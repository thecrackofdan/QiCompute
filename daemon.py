from __future__ import annotations

import argparse
import time
from typing import Any
from uuid import uuid4

import failures
from db import WorkerDB
from receipts import compute_receipt_hash, make_receipt, utc_now_iso
from registry import heartbeat_local_worker, register_local_worker
from reputation import update_worker_reputation
from runners import runner_for_type
from telemetry import GPUTelemetry
from verifier import verify_inference_receipt
from worker import load_config


class WorkerDaemon:
    def __init__(self, config: dict[str, Any], db: WorkerDB, telemetry: GPUTelemetry | None = None):
        self.config = config
        self.db = db
        self.worker_id = config["worker"]["id"]
        self.telemetry = telemetry or GPUTelemetry(
            nvidia_smi_path=config.get("telemetry", {}).get("nvidia_smi_path", "nvidia-smi"),
            fallback_watts=float(config["worker"].get("fallback_watts", 0)),
        )

    def run_once(self, runtime_type: str | None = None) -> dict[str, Any] | None:
        worker = register_local_worker(self.db, self.config)
        heartbeat_local_worker(self.db, self.worker_id, {"source": "daemon", "total_watts": self.telemetry.total_watts()})
        self.db.expire_stale_customer_jobs(utc_now_iso())
        jobs = self.db.list_assigned_jobs(self.worker_id, limit=1)
        if not jobs:
            return None
        job = jobs[0]
        self.db.update_customer_job_status(job["job_id"], "running", {})
        self.db.increment_worker_load(self.worker_id)
        try:
            runtime_cfg = dict(self.config.get("runtime", {}))
            selected_runtime_type = runtime_type or runtime_cfg.get("type", "simulated")
            self.config["runtime"] = {**runtime_cfg, "type": selected_runtime_type}
            runtime = runner_for_type(selected_runtime_type)
            result = runtime.run(job, self.config)
            receipt = self._receipt_from_result(job, result)
            verification = verify_inference_receipt(receipt, _job_for_verifier(job), self.config)
            receipt["metadata"]["verification"] = verification.to_dict()
            receipt["receipt_hash"] = _refresh_receipt_hash(receipt)
            self.db.insert_receipt(receipt)
            update_worker_reputation(
                self.db,
                worker_id=self.worker_id,
                verification=verification.to_dict(),
                receipt=receipt,
            )
            if result.accepted and verification.accepted:
                self.db.update_customer_job_status(job["job_id"], "completed", {"receipt_id": receipt["receipt_id"]})
            else:
                self.db.mark_customer_job_failure(
                    job["job_id"],
                    result.error_code or verification.reason or failures.VERIFICATION_FAILED,
                    result.error_message or verification.metadata.get("reason_detail", "runtime verification failed"),
                )
            return receipt
        finally:
            self.db.decrement_worker_load(self.worker_id)
            heartbeat_local_worker(self.db, self.worker_id, {"source": "daemon", "total_watts": self.telemetry.total_watts()})

    def run_loop(self, runtime_type: str | None = None) -> None:
        interval = float(self.config["worker"].get("loop_interval_seconds", 5))
        while True:
            self.run_once(runtime_type=runtime_type)
            time.sleep(interval)

    def _receipt_from_result(self, job: dict[str, Any], result: Any) -> dict[str, Any]:
        estimated_qi = _estimated_qi(job, result, self.config) if result.accepted else 0.0
        metadata = {
            "job_id": result.job_id,
            "accepted": result.accepted,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "output_hash": result.output_hash,
            "runtime": {
                "type": result.metadata.get("runtime_type"),
                "exit_code": result.exit_code,
                "error_code": result.error_code,
                "error_message": result.error_message,
            },
            "telemetry": {
                "total_watts": result.metadata.get("total_watts"),
                "energy_joules": result.metadata.get("energy_joules"),
                "tokens_per_second": result.metadata.get("tokens_per_second"),
                "model_load_cold_start": result.metadata.get("model_load_cold_start"),
                "cache_hit": result.metadata.get("cache_hit"),
            },
        }
        return make_receipt(
            worker_id=self.worker_id,
            mode="inference",
            started_at=result.started_at,
            ended_at=result.ended_at,
            duration_seconds=max(result.duration_seconds, 0.000001),
            average_watts=float(result.metadata.get("total_watts") or self.config["worker"].get("fallback_watts", 0)),
            output_type="tokens",
            output_amount=result.output_tokens,
            estimated_qi_owed=estimated_qi,
            metadata=metadata,
        ).to_dict()


def main() -> None:
    parser = argparse.ArgumentParser(description="Local QiCompute worker daemon")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--runtime", choices=["simulated", "subprocess", "ollama", "ollama_placeholder", "llama_cpp_placeholder"])
    args = parser.parse_args()

    config = load_config(args.config)
    if args.runtime:
        config["runtime"] = {**config.get("runtime", {}), "type": args.runtime}
    db = WorkerDB(config["worker"]["db_path"])
    try:
        daemon = WorkerDaemon(config, db)
        if args.loop:
            daemon.run_loop(runtime_type=args.runtime)
        else:
            daemon.run_once(runtime_type=args.runtime)
    finally:
        db.close()


def _job_for_verifier(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": job["job_id"],
        "input_tokens": job.get("input_tokens", 0),
        "output_tokens": job.get("expected_output_tokens", 0),
    }


def _estimated_qi(job: dict[str, Any], result: Any, config: dict[str, Any]) -> float:
    inference_cfg = config.get("inference", {})
    fallback_rate = float(inference_cfg.get("estimated_qi_per_token", 0))
    input_rate = float(inference_cfg.get("estimated_qi_per_input_token", fallback_rate))
    output_rate = float(inference_cfg.get("estimated_qi_per_output_token", fallback_rate))
    return float(result.input_tokens) * input_rate + float(result.output_tokens) * output_rate


def _refresh_receipt_hash(receipt: dict[str, Any]) -> str:
    receipt.pop("receipt_hash", None)
    return compute_receipt_hash(receipt)


if __name__ == "__main__":
    main()
