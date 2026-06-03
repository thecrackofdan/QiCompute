from __future__ import annotations

import argparse
from typing import Any

from db import WorkerDB
from economics import compare_inference_vs_mining
from epochs import active_epoch
from receipts import utc_now_iso
from worker import load_config


def cluster_health(db: WorkerDB) -> dict[str, Any]:
    workers = db.list_online_workers()
    all_workers = _all_workers(db)
    jobs = _all_jobs(db)
    events = db.recent_cluster_events(50)
    active = active_epoch(db)
    total_watts = sum(float(worker.get("total_watts_capacity", 0) or 0) for worker in all_workers)
    utilization = len([job for job in jobs if job["status"] in {"routed", "running"}]) / max(1, len(all_workers))
    return {
        "total_workers": len(all_workers),
        "online_workers": len([worker for worker in all_workers if worker.get("online")]),
        "offline_stale_workers": len([worker for worker in all_workers if not worker.get("online")]),
        "queued_jobs": len([job for job in jobs if job["status"] in {"queued", "retrying"}]),
        "routed_running_jobs": len([job for job in jobs if job["status"] in {"routed", "running"}]),
        "expired_leases": len([job for job in jobs if job.get("lease_expires_at") and job["lease_expires_at"] <= utc_now_iso() and job["status"] in {"routed", "running"}]),
        "recent_auth_failures": len([event for event in events if event["event_type"] == "auth_failure"]),
        "recent_receipt_rejections": len([event for event in events if event["event_type"] == "receipt" and not event["accepted"]]),
        "active_epoch": active["epoch_id"],
        "latest_settlement_totals": {
            "total_settled_qi": active.get("total_settled_qi", 0),
            "total_energy_joules": active.get("total_energy_joules", 0),
            "total_tokens": active.get("total_tokens", 0),
        },
        "online_worker_ids": [worker["worker_id"] for worker in workers],
        "economic_comparison": compare_inference_vs_mining(
            gpu_wattage=total_watts,
            energy_cost_per_kwh=0.15,
            inference_utilization=min(utilization, 1.0),
            mining_reward_estimate_qi_per_hour=0.01 * max(1, len(all_workers)),
            average_inference_price_qi=max(float(active.get("total_settled_qi", 0)), 0.0001),
            tokens_per_second=100.0 * max(1, len(workers)),
        ),
    }


def print_cluster_health(summary: dict[str, Any]) -> None:
    for key, value in summary.items():
        print(f"{key}: {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Show local QiCompute cluster health")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    config = load_config(args.config)
    db = WorkerDB(config["worker"]["db_path"])
    try:
        print_cluster_health(cluster_health(db))
    finally:
        db.close()
    return 0


def _all_workers(db: WorkerDB) -> list[dict[str, Any]]:
    rows = db.conn.execute("SELECT * FROM worker_registry ORDER BY worker_id ASC")
    from db import _worker_row_to_dict

    return [_worker_row_to_dict(row) for row in rows]


def _all_jobs(db: WorkerDB) -> list[dict[str, Any]]:
    rows = db.conn.execute("SELECT * FROM customer_jobs ORDER BY created_at ASC")
    from db import _customer_job_row_to_dict

    return [_customer_job_row_to_dict(row) for row in rows]


if __name__ == "__main__":
    raise SystemExit(main())
