from __future__ import annotations

import argparse
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import failures
from abuse import record_rate_limit_event
from accounting_checks import run_accounting_checks
from accounts import create_customer_account, escrow_job_funds, refund_job_escrow
from capabilities import make_capability_claim
from controller import ClusterController
from worker_daemon import receipt_from_runtime_result
from db import WorkerDB
from epochs import active_epoch, finalize_epoch
from perf import MetricsAccumulator, bottleneck_summary, timer
from receipts import utc_now_iso
from runtime import SimulatedRuntime
from treasury import get_treasury, record_refund
from worker import load_config


def run_load_test(
    *,
    workers: int = 10,
    jobs: int = 100,
    seed: int = 42,
    mode: str = "honest",
    db_path: str | None = None,
    config_path: str = "config.demo.yaml",
) -> dict[str, Any]:
    config = load_config(config_path)
    config["runtime"] = {**config.get("runtime", {}), "type": "simulated", "simulated_seconds": 0}
    if db_path is None:
        fd, generated = tempfile.mkstemp(prefix="qicompute-load-", suffix=".db")
        os.close(fd)
        Path(generated).unlink(missing_ok=True)
        db_path = generated
    config["worker"]["db_path"] = db_path
    db = WorkerDB(db_path)
    metrics = MetricsAccumulator()
    started = time.perf_counter()
    attacks_rejected = 0
    double_pays_prevented = 0
    rate_limits_triggered = 0
    try:
        controller = ClusterController(db, config)
        epoch = active_epoch(db)
        runtime = SimulatedRuntime()
        worker_ids = [_register_worker(controller, index, mode) for index in range(max(1, workers))]
        customer_id = "load-customer"
        create_customer_account(db, customer_id, initial_qi=max(1.0, jobs * _estimated_synthetic_price()))

        with timer(metrics, "db_write"):
            for index in range(max(0, jobs)):
                job = _job(index, customer_id)
                db.insert_customer_job(job)
                escrow_job_funds(db, job, job["max_price_qi"])
                if mode in {"mixed", "malicious"} and index % 25 == 0:
                    record_rate_limit_event(db, "customer", customer_id, "job_submission", {"mode": mode})

        route_order = 0
        while True:
            queued = db.list_queued_jobs()
            if not queued:
                break
            worker_id = worker_ids[route_order % len(worker_ids)]
            route_order += 1
            with timer(metrics, "routing"):
                assignment = controller.handle_next_job(worker_id)
            assigned = assignment.get("job")
            if not assigned:
                continue
            if mode in {"flaky", "mixed"} and int(assigned["job_id"].rsplit("-", 1)[-1]) % 17 == 0:
                db.mark_customer_job_failure(assigned["job_id"], failures.COMMAND_FAILED, "synthetic flaky failure")
                refund = refund_job_escrow(db, assigned["job_id"], failures.COMMAND_FAILED)
                if refund.get("refund_qi", 0):
                    record_refund(db, refund_qi=refund["refund_qi"])
                db.decrement_worker_load(worker_id)
                attacks_rejected += 1
                continue
            with timer(metrics, "execution"):
                result = runtime.run(assigned, config)
                receipt = receipt_from_runtime_result(config, assigned["assigned_worker_id"], assigned, result)
            if mode in {"malicious", "mixed"} and int(assigned["job_id"].rsplit("-", 1)[-1]) % 31 == 0:
                replay = controller.handle_receipt(
                    {
                        "worker_id": receipt["worker_id"],
                        "job_id": assigned["job_id"],
                        "lease_id": assigned.get("lease_id"),
                        "receipt": receipt,
                    }
                )
                if replay.get("accepted"):
                    duplicate = controller.handle_receipt(
                        {
                            "worker_id": receipt["worker_id"],
                            "job_id": assigned["job_id"],
                            "lease_id": assigned.get("lease_id"),
                            "receipt": receipt,
                        }
                    )
                    if duplicate.get("failure_code") == failures.DUPLICATE_RECEIPT:
                        double_pays_prevented += 1
                        attacks_rejected += 1
                    continue
            with timer(metrics, "verification"):
                response = controller.handle_receipt(
                    {
                        "worker_id": receipt["worker_id"],
                        "job_id": assigned["job_id"],
                        "lease_id": assigned.get("lease_id"),
                        "receipt": receipt,
                    }
                )
            if not response.get("accepted"):
                attacks_rejected += 1

        with timer(metrics, "settlement"):
            finalized = finalize_epoch(db, epoch["epoch_id"])
        elapsed = max(time.perf_counter() - started, 0.000001)
        rows = _job_counts(db)
        treasury = get_treasury(db)
        stage_totals = {name: summary["total"] for name, summary in metrics.summaries().items()}
        rate_limits_triggered = db.rate_limit_count("customer", customer_id, "job_submission", "1970-01-01T00:00:00+00:00")
        reconciliation = "PASS" if all(check.status != "FAIL" for check in run_accounting_checks(db, mode="quick")) else "FAIL"
        return {
            "workers": workers,
            "jobs_submitted": jobs,
            "jobs_completed": rows.get("completed", 0),
            "jobs_failed": rows.get("failed", 0),
            "jobs_refunded": _count(db, "SELECT COUNT(*) FROM job_escrows WHERE status = 'refunded'"),
            "jobs_disputed": _count(db, "SELECT COUNT(*) FROM job_escrows WHERE status = 'disputed'"),
            "throughput_jobs_sec": jobs / elapsed,
            "average_queue_latency": 0.0,
            "route_latency": metrics.summary("routing"),
            "execution_latency": metrics.summary("execution"),
            "average_worker_utilization": _average_worker_utilization(db),
            "total_settled_qi": treasury["total_settled_volume"],
            "total_refunded_qi": treasury["total_customer_refunds"],
            "treasury_fees": treasury["total_fees_collected"],
            "db_size_bytes": Path(db_path).stat().st_size if Path(db_path).exists() else 0,
            "attacks_rejected": attacks_rejected,
            "double_pays_prevented": double_pays_prevented,
            "rate_limits_triggered": rate_limits_triggered,
            "committee_disputes": 0,
            "accounting_reconciliation": reconciliation,
            "stage_metrics": metrics.summaries(),
            "bottleneck": bottleneck_summary(stage_totals),
            "epoch": finalized,
        }
    finally:
        db.close()


def print_load_report(result: dict[str, Any]) -> None:
    fields = (
        "jobs_submitted",
        "jobs_completed",
        "jobs_failed",
        "jobs_refunded",
        "jobs_disputed",
        "throughput_jobs_sec",
        "average_queue_latency",
        "average_worker_utilization",
        "total_settled_qi",
        "total_refunded_qi",
        "treasury_fees",
        "db_size_bytes",
        "attacks_rejected",
        "double_pays_prevented",
        "rate_limits_triggered",
        "committee_disputes",
        "accounting_reconciliation",
    )
    print("QiCompute Synthetic Load Test")
    for field in fields:
        print(f"{field}: {result.get(field)}")
    route = result["route_latency"]
    execution = result["execution_latency"]
    print(f"route_latency_p50: {route['p50']:.6f}")
    print(f"route_latency_p95: {route['p95']:.6f}")
    print(f"route_latency_p99: {route['p99']:.6f}")
    print(f"execution_latency_p50: {execution['p50']:.6f}")
    print(f"execution_latency_p95: {execution['p95']:.6f}")
    print(f"execution_latency_p99: {execution['p99']:.6f}")
    print(f"slowest_stage: {result['bottleneck']['slowest_stage']}")
    print(f"recommendation: {result['bottleneck']['recommendation']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a deterministic QiCompute synthetic load test")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--jobs", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--mode", choices=("honest", "flaky", "malicious", "mixed"), default="honest")
    parser.add_argument("--db-path")
    parser.add_argument("--config", default="config.demo.yaml")
    args = parser.parse_args()
    result = run_load_test(
        workers=max(1, args.workers),
        jobs=max(0, args.jobs),
        seed=args.seed,
        mode=args.mode,
        db_path=args.db_path,
        config_path=args.config,
    )
    print_load_report(result)
    return 0


def _register_worker(controller: ClusterController, index: int, mode: str) -> str:
    worker_id = f"load-worker-{index:03d}"
    worker = {
        "worker_id": worker_id,
        "operator": f"operator-{index % 5}",
        "region": "local",
        "public_key": "placeholder-public-key",
        "endpoint": "local",
        "hardware_profile": {"gpu_count": 1, "gpu_names": ["simulated"], "total_vram_gb": 24},
        "supported_modes": ["inference", "mining"],
        "supported_models": ["llama-3.1-8b", "mistral-7b"],
        "gpu_count": 1,
        "total_vram_gb": 24,
        "total_watts_capacity": 250,
        "online": not (mode == "mixed" and index % 19 == 0),
        "last_seen_at": utc_now_iso(),
        "max_concurrent_jobs": 2,
        "metadata": {"loaded_models": ["llama-3.1-8b"] if index % 2 == 0 else ["mistral-7b"]},
    }
    controller.handle_capability({"worker_id": worker_id, "worker": worker, "capability_claim": make_capability_claim(worker)})
    controller.handle_heartbeat({"worker_id": worker_id, "telemetry": {"last_seen_at": utc_now_iso(), "source": "load-test"}})
    return worker_id


def _job(index: int, customer_id: str) -> dict[str, Any]:
    return {
        "job_id": f"load-job-{index}",
        "customer_id": customer_id,
        "model": "llama-3.1-8b" if index % 2 == 0 else "mistral-7b",
        "prompt_hash": f"load-prompt-hash-{index}",
        "input_tokens": 16,
        "expected_output_tokens": 32,
        "privacy_level": "standard",
        "max_price_qi": _estimated_synthetic_price(),
        "status": "queued",
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "metadata": {"source": "load_test"},
    }


def _estimated_synthetic_price() -> float:
    return round(16 * 0.00000005 + 32 * 0.0000002, 12)


def _job_counts(db: WorkerDB) -> dict[str, int]:
    rows = db.conn.execute("SELECT status, COUNT(*) AS count FROM customer_jobs GROUP BY status").fetchall()
    return {row["status"]: int(row["count"]) for row in rows}


def _count(db: WorkerDB, sql: str) -> int:
    row = db.conn.execute(sql).fetchone()
    return int(row[0] if row else 0)


def _average_worker_utilization(db: WorkerDB) -> float:
    row = db.conn.execute("SELECT COALESCE(AVG(load_percent), 0) FROM worker_registry").fetchone()
    return float(row[0] if row else 0.0)


if __name__ == "__main__":
    raise SystemExit(main())
