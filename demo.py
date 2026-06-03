from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import failures
from daemon import WorkerDaemon
from db import WorkerDB
from demo_data import demo_job, demo_prompt, demo_workers
from epochs import active_epoch, finalize_epoch
from receipts import utc_now_iso
from registry import heartbeat_local_worker
from router import route_and_audit_inference_job
from summary import print_committee_summary, print_epoch_summary, print_job_summary, print_worker_summary
from telemetry import GPUTelemetry
from worker import load_config


def run_demo(
    *,
    mode: str = "honest",
    config_path: str = "config.demo.yaml",
    db_path: str | None = None,
    reset_db: bool = True,
) -> dict[str, Any]:
    if mode not in {"honest", "flaky", "malicious"}:
        raise ValueError("mode must be one of: honest, flaky, malicious")
    config = load_config(config_path)
    if db_path:
        config["worker"]["db_path"] = db_path
    db_file = Path(config["worker"]["db_path"])
    if reset_db and db_file.exists():
        db_file.unlink()
    if mode == "flaky":
        config["runtime"]["ollama_url"] = "http://127.0.0.1:1/api/generate"

    db = WorkerDB(config["worker"]["db_path"])
    try:
        for worker in demo_workers(config):
            db.register_worker(worker)
            heartbeat_local_worker(db, worker["worker_id"], {"source": "demo", "last_seen_at": utc_now_iso()})
        epoch = active_epoch(db)
        job = demo_job(mode)
        db.insert_customer_job(job)
        decision = route_and_audit_inference_job(
            db,
            {**job, "requires_gpu": True},
            [db.get_worker(config["worker"]["id"])],
        )
        if not decision.accepted or not decision.worker_id:
            db.update_customer_job_status(job["job_id"], "rejected", {"failure_code": decision.failure_code})
        else:
            db.assign_customer_job(job["job_id"], decision.worker_id, decision.score)
            job_override = {"prompt": demo_prompt(mode)}
            if mode == "malicious":
                job_override["challenge_response_hash"] = "malicious-demo-response"
            overrides = {job["job_id"]: job_override}
            daemon = WorkerDaemon(
                config,
                db,
                telemetry=GPUTelemetry(
                    nvidia_smi_path=config.get("telemetry", {}).get("nvidia_smi_path", "nvidia-smi"),
                    fallback_watts=float(config["worker"].get("fallback_watts", 250)),
                ),
                job_overrides=overrides,
            )
            daemon.run_once(runtime_type=config["runtime"].get("type", "ollama"))

        finalized = finalize_epoch(db, epoch["epoch_id"])
        stored_job = db.get_customer_job(job["job_id"])
        receipt = _latest_receipt_for_job(db, job["job_id"])
        committee = _latest_committee_for_job(db, job["job_id"])
        metrics = _metrics(db, finalized, stored_job, receipt, committee)
        _print_demo_summary(db, finalized, stored_job, receipt, committee, metrics, config["worker"]["id"])
        return {
            "epoch": finalized,
            "job": stored_job,
            "receipt": receipt,
            "committee": committee,
            "metrics": metrics,
            "worker": db.get_worker(config["worker"]["id"]),
        }
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="QiCompute local end-to-end inference demo")
    parser.add_argument("--config", default="config.demo.yaml")
    parser.add_argument("--mode", choices=["honest", "flaky", "malicious"], default="honest")
    parser.add_argument("--db-path")
    parser.add_argument("--keep-db", action="store_true")
    args = parser.parse_args()
    run_demo(mode=args.mode, config_path=args.config, db_path=args.db_path, reset_db=not args.keep_db)


def _latest_receipt_for_job(db: WorkerDB, job_id: str) -> dict[str, Any] | None:
    rows = db.conn.execute(
        "SELECT * FROM receipts WHERE job_id = ? ORDER BY ended_at DESC LIMIT 1",
        (job_id,),
    ).fetchall()
    if not rows:
        return None
    row = rows[0]
    return {
        "receipt_id": row["receipt_id"],
        "worker_id": row["worker_id"],
        "energy_joules": row["energy_joules"],
        "output_amount": row["output_amount"],
        "estimated_qi_owed": row["estimated_qi_owed"],
        "metadata": json.loads(row["metadata_json"]),
    }


def _latest_committee_for_job(db: WorkerDB, job_id: str) -> dict[str, Any] | None:
    rows = db.conn.execute(
        """
        SELECT * FROM verification_committees
        WHERE json_extract(metadata_json, '$.job_id') = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (job_id,),
    ).fetchall()
    return db.verification_committee(rows[0]["committee_id"]) if rows else None


def _metrics(
    db: WorkerDB,
    epoch: dict[str, Any],
    job: dict[str, Any],
    receipt: dict[str, Any] | None,
    committee: dict[str, Any] | None,
) -> dict[str, Any]:
    challenge_results = db.challenge_results_for_job(job["job_id"])
    runtime_type = receipt.get("metadata", {}).get("runtime", {}).get("type") if receipt else None
    rejected_qi = 0.0 if job["status"] == "completed" or not receipt else float(receipt.get("estimated_qi_owed", 0))
    latency = db.get_worker(job["assigned_worker_id"])["average_latency_ms"] if job.get("assigned_worker_id") else 0
    energy_per_token = db.get_worker(job["assigned_worker_id"])["average_energy_per_token"] if job.get("assigned_worker_id") else 0
    return {
        "jobs_submitted": 1,
        "jobs_completed": 1 if job["status"] == "completed" else 0,
        "jobs_rejected": 1 if job["status"] in {"failed", "rejected"} else 0,
        "jobs_disputed": 1 if committee and committee.get("result") == "disputed" else 0,
        "challenge_pass_rate": sum(1 for result in challenge_results if result["accepted"]) / len(challenge_results) if challenge_results else 0,
        "committee_acceptance_rate": 1.0 if committee and committee.get("result") == "accepted" else 0.0,
        "settled_qi_total": epoch["total_settled_qi"],
        "rejected_qi_total": rejected_qi,
        "average_latency": latency,
        "average_energy_per_token": energy_per_token,
        "mining_fallback_utilization": 0.0,
        "runtime_type_distribution": {runtime_type or "none": 1},
    }


def _print_demo_summary(
    db: WorkerDB,
    epoch: dict[str, Any],
    job: dict[str, Any],
    receipt: dict[str, Any] | None,
    committee: dict[str, Any] | None,
    metrics: dict[str, Any],
    worker_id: str,
) -> None:
    print("QiCompute Local End-to-End Demo")
    print_epoch_summary(epoch)
    print_worker_summary(db.get_worker(worker_id))
    job_summary = _job_summary(job, receipt, committee)
    print_job_summary(job_summary)
    print_committee_summary(committee or {})
    print("Marketplace Metrics")
    for key, value in metrics.items():
        print(f"  {key}: {value}")


def _job_summary(job: dict[str, Any], receipt: dict[str, Any] | None, committee: dict[str, Any] | None) -> dict[str, Any]:
    metadata = {}
    if receipt:
        receipt_metadata = receipt.get("metadata", {})
        metadata["runtime_type"] = receipt_metadata.get("runtime", {}).get("type")
        metadata["verification_outcome"] = receipt_metadata.get("verification", {}).get("reason")
        metadata["challenge_outcome"] = receipt_metadata.get("challenge_verification", {}).get("reason")
    metadata["committee_outcome"] = committee.get("result") if committee else None
    metadata["payout_eligible"] = job.get("status") == "completed"
    return {**job, "metadata": metadata}


if __name__ == "__main__":
    main()
