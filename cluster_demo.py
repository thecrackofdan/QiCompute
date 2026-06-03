from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from capabilities import make_capability_claim
from controller import ClusterController
from daemon import receipt_from_runtime_result
from db import WorkerDB
from demo_data import demo_job, demo_workers
from epochs import active_epoch, finalize_epoch
from receipts import utc_now_iso
from registry import worker_from_config
from runtime import SimulatedRuntime
from summary import print_epoch_summary, print_job_summary, print_worker_summary
from worker import load_config


def run_cluster_demo(config_path: str = "config.demo.yaml", db_path: str | None = None, reset_db: bool = True) -> dict[str, Any]:
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
        worker_configs = _worker_configs(config)
        for worker_config in worker_configs:
            worker = worker_from_config(worker_config)
            controller.handle_capability({"worker_id": worker["worker_id"], "worker": worker, "capability_claim": make_capability_claim(worker)})
            controller.handle_heartbeat({"worker_id": worker["worker_id"], "telemetry": {"last_seen_at": utc_now_iso(), "source": "cluster-demo"}})
        job = demo_job("honest")
        db.insert_customer_job(job)
        next_job = controller.handle_next_job(worker_configs[0]["worker"]["id"])
        assigned_job = next_job["job"]
        result = SimulatedRuntime().run(assigned_job, config)
        receipt = receipt_from_runtime_result(config, assigned_job["assigned_worker_id"], assigned_job, result)
        receipt_result = controller.handle_receipt({"worker_id": receipt["worker_id"], "job_id": assigned_job["job_id"], "receipt": receipt})
        epoch = finalize_epoch(db, active["epoch_id"])
        stored_job = db.get_customer_job(job["job_id"])
        events = db.recent_cluster_events(20)
        _print_cluster_demo(db, epoch, stored_job, events)
        return {
            "epoch": epoch,
            "job": stored_job,
            "receipt_result": receipt_result,
            "events": events,
            "workers": [db.get_worker(worker_config["worker"]["id"]) for worker_config in worker_configs],
        }
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a deterministic local QiCompute cluster demo")
    parser.add_argument("--config", default="config.demo.yaml")
    parser.add_argument("--db-path")
    parser.add_argument("--keep-db", action="store_true")
    args = parser.parse_args()
    run_cluster_demo(config_path=args.config, db_path=args.db_path, reset_db=not args.keep_db)


def _worker_configs(config: dict[str, Any]) -> list[dict[str, Any]]:
    configs = []
    for index, worker in enumerate(demo_workers(config)[:2], start=1):
        worker_config = json.loads(json.dumps(config))
        worker_config["worker"]["id"] = worker["worker_id"]
        worker_config["worker"]["operator"] = worker["operator"]
        worker_config["worker"]["public_key"] = worker["public_key"]
        worker_config["worker"]["region"] = worker["region"]
        worker_config["worker"]["hardware_profile"] = worker["hardware_profile"]
        worker_config["worker"]["supported_modes"] = worker["supported_modes"]
        worker_config["worker"]["supported_models"] = worker["supported_models"]
        worker_config["worker"]["fallback_watts"] = worker["total_watts_capacity"] or 250
        worker_config["worker"]["db_path"] = config["worker"]["db_path"]
        worker_config["worker"]["cluster_index"] = index
        configs.append(worker_config)
    return configs


def _print_cluster_demo(db: WorkerDB, epoch: dict[str, Any], job: dict[str, Any], events: list[dict[str, Any]]) -> None:
    print("QiCompute Local LAN Cluster Demo")
    print_epoch_summary(epoch)
    if job.get("assigned_worker_id"):
        worker = db.get_worker(job["assigned_worker_id"])
        if worker:
            print_worker_summary(worker)
    print_job_summary({**job, "metadata": {"payout_eligible": job["status"] == "completed", "runtime_type": "simulated"}})
    print("Cluster Events")
    for event in reversed(events[-8:]):
        print(
            f"  {event['event_type']} worker={event['worker_id']} job={event['job_id']} "
            f"accepted={event['accepted']} failure={event['failure_code']}"
        )


if __name__ == "__main__":
    main()
