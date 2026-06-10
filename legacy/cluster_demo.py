from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from accounts import create_customer_account, escrow_job_funds
from capabilities import make_capability_claim
from controller import ClusterController
from worker_daemon import receipt_from_runtime_result
from db import WorkerDB
from demo_data import demo_job, demo_workers
from epochs import active_epoch, finalize_epoch
from receipts import utc_now_iso
from registry import worker_from_config
from runtime import SimulatedRuntime
from summary import print_epoch_summary, print_job_summary, print_worker_summary
from treasury import get_treasury
from worker import load_config


def run_cluster_demo(
    config_path: str = "config.demo.yaml",
    db_path: str | None = None,
    reset_db: bool = True,
    worker_count: int = 2,
    job_count: int = 1,
    simulate_worker_failure: bool = False,
) -> dict[str, Any]:
    config = load_config(config_path)
    config["runtime"] = {**config.get("runtime", {}), "type": "simulated"}
    if db_path:
        config["worker"]["db_path"] = db_path
    db_file = Path(config["worker"]["db_path"])
    if reset_db and db_file.exists():
        db_file.unlink()
    db = WorkerDB(config["worker"]["db_path"])
    try:
        controller = ClusterController(db, config)
        active = active_epoch(db)
        worker_configs = _worker_configs(config, worker_count)
        for worker_config in worker_configs:
            worker = worker_from_config(worker_config)
            controller.handle_capability({"worker_id": worker["worker_id"], "worker": worker, "capability_claim": make_capability_claim(worker)})
            controller.handle_heartbeat({"worker_id": worker["worker_id"], "telemetry": {"last_seen_at": utc_now_iso(), "source": "cluster-demo"}})

        for index in range(job_count):
            job = {**demo_job("honest"), "job_id": f"demo-cluster-job-{index}", "model": _model_for_index(index)}
            if index == 0:
                create_customer_account(db, job["customer_id"], initial_qi=float(job["max_price_qi"]) * max(1, job_count) + 0.000001)
            db.insert_customer_job(job)
            escrow_job_funds(db, job, job["max_price_qi"])

        metrics = {
            "jobs_completed": 0,
            "reassigned_jobs": 0,
            "lease_expirations": 0,
            "challenge_failures": 0,
            "committee_disputes": 0,
            "average_worker_utilization": 0.0,
            "average_queue_latency": 0.0,
            "total_settled_qi": 0.0,
        }

        worker_index = 0
        while True:
            queued = db.list_queued_jobs()
            if not queued:
                break
            worker_config = worker_configs[worker_index % len(worker_configs)]
            worker_id = worker_config["worker"]["id"]
            worker_index += 1
            next_job = controller.handle_next_job(worker_id)
            assigned_job = next_job.get("job")
            if not assigned_job:
                continue
            if simulate_worker_failure and metrics["lease_expirations"] == 0:
                db.conn.execute("UPDATE customer_jobs SET lease_expires_at = ? WHERE job_id = ?", ("2020-01-01T00:00:00Z", assigned_job["job_id"]))
                db.conn.commit()
                expired = db.requeue_expired_leased_jobs("2020-01-01T00:00:01Z")
                metrics["lease_expirations"] += expired
                metrics["reassigned_jobs"] += expired
                continue
            result = SimulatedRuntime().run(assigned_job, config)
            receipt = receipt_from_runtime_result(config, assigned_job["assigned_worker_id"], assigned_job, result)
            controller.handle_receipt(
                {
                    "worker_id": receipt["worker_id"],
                    "job_id": assigned_job["job_id"],
                    "lease_id": assigned_job.get("lease_id"),
                    "receipt": receipt,
                }
            )

        epoch = finalize_epoch(db, active["epoch_id"])
        jobs = _jobs(db)
        events = db.recent_cluster_events(50)
        workers = [db.get_worker(worker_config["worker"]["id"]) for worker_config in worker_configs]
        metrics["jobs_completed"] = len([job for job in jobs if job["status"] == "completed"])
        metrics["total_settled_qi"] = epoch["total_settled_qi"]
        treasury = get_treasury(db)
        metrics["marketplace_fees_collected"] = treasury["total_fees_collected"]
        metrics["worker_payouts"] = treasury["total_worker_payouts"]
        metrics["customer_refunds"] = treasury["total_customer_refunds"]
        metrics["average_worker_utilization"] = sum(float(worker.get("load_percent", 0) or 0) for worker in workers if worker) / max(1, len(workers))
        _print_cluster_demo(db, epoch, jobs[-1] if jobs else {}, events, metrics)
        return {
            "epoch": epoch,
            "job": jobs[-1] if jobs else None,
            "jobs": jobs,
            "metrics": metrics,
            "events": events,
            "workers": workers,
        }
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a deterministic local QiCompute cluster demo")
    parser.add_argument("--config", default="config.demo.yaml")
    parser.add_argument("--db-path")
    parser.add_argument("--keep-db", action="store_true")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--simulate-worker-failure", action="store_true")
    args = parser.parse_args()
    run_cluster_demo(
        config_path=args.config,
        db_path=args.db_path,
        reset_db=not args.keep_db,
        worker_count=max(1, args.workers),
        job_count=max(1, args.jobs),
        simulate_worker_failure=args.simulate_worker_failure,
    )


def _worker_configs(config: dict[str, Any], worker_count: int = 2) -> list[dict[str, Any]]:
    source_workers = demo_workers(config)
    configs = []
    for index in range(worker_count):
        worker = source_workers[index % len(source_workers)]
        worker_config = json.loads(json.dumps(config))
        worker_config["worker"]["id"] = worker["worker_id"] if index < len(source_workers) else f"demo-worker-{index}"
        worker_config["worker"]["operator"] = worker["operator"]
        worker_config["worker"]["public_key"] = worker["public_key"]
        worker_config["worker"]["region"] = worker["region"]
        worker_config["worker"]["hardware_profile"] = worker["hardware_profile"]
        worker_config["worker"]["supported_modes"] = worker["supported_modes"]
        worker_config["worker"]["supported_models"] = ["llama-3.1-8b", "mistral-7b"]
        worker_config["worker"]["fallback_watts"] = worker["total_watts_capacity"] or 250
        worker_config["worker"]["db_path"] = config["worker"]["db_path"]
        worker_config["worker"]["cluster_index"] = index + 1
        worker_config["worker"]["max_concurrent_jobs"] = 2
        configs.append(worker_config)
    return configs


def _print_cluster_demo(db: WorkerDB, epoch: dict[str, Any], job: dict[str, Any], events: list[dict[str, Any]], metrics: dict[str, Any]) -> None:
    print("QiCompute Local LAN Cluster Demo")
    print_epoch_summary(epoch)
    if job and job.get("assigned_worker_id"):
        worker = db.get_worker(job["assigned_worker_id"])
        if worker:
            print_worker_summary(worker)
    if job:
        print_job_summary({**job, "metadata": {"payout_eligible": job["status"] == "completed", "runtime_type": "simulated"}})
    print("Cluster Metrics")
    for key, value in metrics.items():
        print(f"  {key}: {value}")
    print("Cluster Events")
    for event in reversed(events[-8:]):
        print(
            f"  {event['event_type']} worker={event['worker_id']} job={event['job_id']} "
            f"accepted={event['accepted']} failure={event['failure_code']}"
        )


def _model_for_index(index: int) -> str:
    return "llama-3.1-8b" if index % 2 == 0 else "mistral-7b"


def _jobs(db: WorkerDB) -> list[dict[str, Any]]:
    rows = db.conn.execute("SELECT * FROM customer_jobs ORDER BY created_at ASC")
    from db import _customer_job_row_to_dict

    return [_customer_job_row_to_dict(row) for row in rows]


if __name__ == "__main__":
    main()
