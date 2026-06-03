from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from uuid import uuid4

import failures
from accounts import record_worker_rejected, refund_job_escrow, settle_job_escrow
from capabilities import make_capability_claim
from challenges import build_challenge_result, create_challenge, should_attach_challenge, verify_challenge_result
from committees import ACCEPTED, create_verification_committee, run_verification_committee
from db import WorkerDB
from epochs import active_epoch
from logging_config import configure_logging, log_event
from privacy import redact_sensitive_fields
from receipts import compute_receipt_hash, make_receipt, utc_now_iso
from registry import heartbeat_local_worker, register_local_worker, worker_from_config
from reputation import update_worker_reputation
from runners import runner_for_type
from telemetry import GPUTelemetry
from treasury import record_refund, record_settlement
from transport import get_json, post_json
from verifier import verify_inference_receipt
from worker import load_config


class WorkerDaemon:
    def __init__(
        self,
        config: dict[str, Any],
        db: WorkerDB,
        telemetry: GPUTelemetry | None = None,
        job_overrides: dict[str, dict[str, Any]] | None = None,
    ):
        self.config = config
        self.db = db
        self.worker_id = config["worker"]["id"]
        self.job_overrides = job_overrides or {}
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
        stored_job = jobs[0]
        job = {**stored_job, **self.job_overrides.get(stored_job["job_id"], {})}
        self.db.update_customer_job_status(stored_job["job_id"], "running", {})
        self.db.increment_worker_load(self.worker_id)
        try:
            runtime_cfg = dict(self.config.get("runtime", {}))
            selected_runtime_type = runtime_type or runtime_cfg.get("type", "simulated")
            self.config["runtime"] = {**runtime_cfg, "type": selected_runtime_type}
            runtime = runner_for_type(selected_runtime_type)
            result = runtime.run(job, self.config)
            challenge = None
            challenge_result = None
            receipt = self._receipt_from_result(job, result)
            if result.accepted and should_attach_challenge(_job_for_challenge(job), self.config):
                challenge = create_challenge(_job_for_challenge(job), self.worker_id, self.config)
                self.db.insert_challenge(challenge)
                receipt["metadata"]["challenge_id"] = challenge["challenge_id"]
                receipt["metadata"]["challenge_response_hash"] = job.get("challenge_response_hash") or challenge[
                    "expected_hash"
                ]
                receipt["receipt_hash"] = _refresh_receipt_hash(receipt)
            verification = verify_inference_receipt(receipt, _job_for_verifier(job), self.config)
            if not result.accepted:
                verification = _verification_failure(
                    result.error_code or failures.COMMAND_FAILED,
                    job,
                    receipt,
                    {
                        "runtime": receipt["metadata"].get("runtime", {}),
                        "payout_eligible": False,
                    },
                )
            if challenge:
                challenge_verification = verify_challenge_result(challenge, receipt)
                challenge_result = build_challenge_result(challenge, receipt, challenge_verification)
                self.db.record_challenge_result(challenge_result)
                receipt["metadata"]["challenge_verification"] = challenge_verification.to_dict()
                if not challenge_verification.accepted:
                    verification = _verification_failure(
                        failures.CHALLENGE_FAILED
                        if challenge_verification.reason != failures.CHALLENGE_EXPIRED
                        else failures.CHALLENGE_EXPIRED,
                        job,
                        receipt,
                        {"challenge": challenge_verification.to_dict(), "payout_eligible": False},
                    )
            if result.accepted and verification.accepted and self.config.get("committees", {}).get("enabled", False):
                receipt["receipt_hash"] = _refresh_receipt_hash(receipt)
                committee_cfg = self.config.get("committees", {})
                epoch = active_epoch(self.db)
                committee = create_verification_committee(
                    self.db,
                    challenge_id=challenge["challenge_id"] if challenge else None,
                    assigned_worker_id=self.worker_id,
                    committee_size=int(committee_cfg.get("committee_size", 3)),
                    quorum_threshold=int(committee_cfg.get("quorum_threshold", 2)),
                    metadata={"job_id": job["job_id"], "epoch_id": epoch["epoch_id"]},
                )
                committee_result = run_verification_committee(
                    self.db,
                    committee,
                    receipt=receipt,
                    challenge_result=challenge_result,
                    forced_votes=committee_cfg.get("forced_votes"),
                )
                receipt["metadata"]["committee_verification"] = {
                    "committee_id": committee_result["committee_id"],
                    "result": committee_result["result"],
                    "vote_counts": committee_result["metadata"].get("vote_counts", {}),
                }
                if committee_result["result"] != ACCEPTED:
                    verification = _verification_failure(
                        failures.COMMITTEE_REJECTED
                        if committee_result["result"] == "rejected"
                        else failures.COMMITTEE_DISPUTED,
                        job,
                        receipt,
                        {"committee": receipt["metadata"]["committee_verification"], "payout_eligible": False},
                    )
            receipt["metadata"]["verification"] = verification.to_dict()
            receipt["receipt_hash"] = _refresh_receipt_hash(receipt)
            self.db.insert_receipt(receipt)
            update_worker_reputation(
                self.db,
                worker_id=self.worker_id,
                verification=verification.to_dict(),
                receipt=receipt,
            )
            payout_eligible = result.accepted and verification.accepted
            if payout_eligible:
                epoch = active_epoch(self.db)
                settlement = settle_job_escrow(
                    self.db,
                    job["job_id"],
                    self.worker_id,
                    receipt["estimated_qi_owed"],
                    float(self.config.get("marketplace", {}).get("fee_percent", 0)),
                )
                record_settlement(
                    self.db,
                    fee_qi=settlement["fee_qi"],
                    worker_payout_qi=settlement["worker_payout_qi"],
                    settled_qi=settlement["settled_qi"],
                )
                payout_event = {
                    "event_id": str(uuid4()),
                    "worker_id": self.worker_id,
                    "event_type": "inference_job",
                    "basis": "daemon_verified_runtime",
                    "qi_amount": settlement["worker_payout_qi"],
                    "created_at": utc_now_iso(),
                    "source_id": receipt["receipt_id"],
                    "epoch_id": epoch["epoch_id"],
                    "metadata": {
                        "job_id": job["job_id"],
                        "runtime_type": result.metadata.get("runtime_type"),
                        "verification_reason": verification.reason,
                        "challenge_id": receipt["metadata"].get("challenge_id"),
                        "committee_id": receipt["metadata"].get("committee_verification", {}).get("committee_id"),
                        "settled_qi": settlement["settled_qi"],
                        "fee_qi": settlement["fee_qi"],
                    },
                }
                self.db.insert_payout_event(payout_event)
                self.db.record_inference_job_paid(
                    job_id=job["job_id"],
                    worker_id=self.worker_id,
                    receipt_id=receipt["receipt_id"],
                    accepted_at=payout_event["created_at"],
                    payout_event_id=payout_event["event_id"],
                )
                self.db.update_customer_job_status(job["job_id"], "completed", {"receipt_id": receipt["receipt_id"]})
            else:
                refund = refund_job_escrow(
                    self.db,
                    job["job_id"],
                    "disputed" if verification.reason == failures.COMMITTEE_DISPUTED else verification.reason or failures.VERIFICATION_FAILED,
                )
                record_refund(self.db, refund_qi=refund.get("refund_qi", 0), disputed=verification.reason == failures.COMMITTEE_DISPUTED)
                record_worker_rejected(self.db, self.worker_id, receipt.get("estimated_qi_owed", 0), disputed=verification.reason == failures.COMMITTEE_DISPUTED)
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
        return receipt_from_runtime_result(self.config, self.worker_id, job, result)


class ClusterWorkerClient:
    def __init__(self, config: dict[str, Any], telemetry: GPUTelemetry | None = None):
        self.config = config
        self.worker_id = config["worker"]["id"]
        cluster_cfg = config.get("cluster", {})
        self.controller_url = cluster_cfg.get("controller_url", "http://127.0.0.1:8080").rstrip("/")
        self.secret = cluster_cfg.get("shared_secret", "dev-local-secret")
        self.timeout = float(cluster_cfg.get("request_timeout_seconds", 5))
        self.telemetry = telemetry or GPUTelemetry(
            nvidia_smi_path=config.get("telemetry", {}).get("nvidia_smi_path", "nvidia-smi"),
            fallback_watts=float(config["worker"].get("fallback_watts", 0)),
        )

    def register_capability(self) -> dict[str, Any]:
        worker = worker_from_config(self.config)
        claim = make_capability_claim(worker)
        return post_json(
            f"{self.controller_url}/capability",
            {"worker_id": self.worker_id, "worker": worker, "capability_claim": claim},
            self.secret,
            timeout=self.timeout,
        )

    def heartbeat(self) -> dict[str, Any]:
        return post_json(
            f"{self.controller_url}/heartbeat",
            {"worker_id": self.worker_id, "telemetry": {"last_seen_at": utc_now_iso(), "total_watts": self.telemetry.total_watts()}},
            self.secret,
            timeout=self.timeout,
        )

    def next_job(self) -> dict[str, Any]:
        return get_json(
            f"{self.controller_url}/job/next?worker_id={self.worker_id}",
            {"worker_id": self.worker_id},
            self.secret,
            timeout=self.timeout,
        )

    def submit_receipt(self, receipt: dict[str, Any], lease_id: str | None = None) -> dict[str, Any]:
        return post_json(
            f"{self.controller_url}/receipt",
            {
                "worker_id": self.worker_id,
                "job_id": receipt.get("metadata", {}).get("job_id"),
                "lease_id": lease_id,
                "receipt": _redact_receipt_for_cluster(receipt),
            },
            self.secret,
            timeout=self.timeout,
        )

    def run_once(self, runtime_type: str | None = None) -> dict[str, Any]:
        capability = self.register_capability()
        heartbeat = self.heartbeat()
        next_job = self.next_job()
        job = next_job.get("job")
        if not job:
            return {"accepted": True, "status": "no_job", "capability": capability, "heartbeat": heartbeat, "next_job": next_job}
        result = self._execute_job(job, runtime_type=runtime_type)
        return {"accepted": bool(result["submission"].get("accepted")), "status": "submitted", **result}

    def run_available(self, runtime_type: str | None = None, max_jobs: int | None = None) -> list[dict[str, Any]]:
        self.register_capability()
        self.heartbeat()
        slots = max_jobs or int(self.config.get("runtime", {}).get("max_concurrent_jobs", self.config.get("worker", {}).get("max_concurrent_jobs", 1)))
        jobs = []
        for _ in range(max(1, slots)):
            next_job = self.next_job()
            if not next_job.get("job"):
                break
            jobs.append(next_job["job"])
        if not jobs:
            return [{"accepted": True, "status": "no_job"}]
        results: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
            futures = [executor.submit(self._execute_job, job, runtime_type) for job in jobs]
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append({"accepted": bool(result["submission"].get("accepted")), "status": "submitted", **result})
                except Exception as exc:
                    results.append({"accepted": False, "status": "failed", "error": str(exc)})
        return results

    def _execute_job(self, job: dict[str, Any], runtime_type: str | None = None) -> dict[str, Any]:
        runtime_cfg = dict(self.config.get("runtime", {}))
        selected_runtime_type = runtime_type or runtime_cfg.get("type", "simulated")
        self.config["runtime"] = {**runtime_cfg, "type": selected_runtime_type}
        runtime = runner_for_type(selected_runtime_type)
        result = runtime.run(job, self.config)
        receipt = receipt_from_runtime_result(self.config, self.worker_id, job, result)
        submission = self.submit_receipt(receipt, lease_id=job.get("lease_id"))
        return {"job": job, "receipt": receipt, "submission": submission}


def main() -> None:
    parser = argparse.ArgumentParser(description="Local QiCompute worker daemon")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--cluster-worker", action="store_true")
    parser.add_argument("--runtime", choices=["simulated", "subprocess", "ollama", "ollama_placeholder", "llama_cpp_placeholder"])
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    logger = configure_logging(verbose=args.verbose, quiet=args.quiet)

    config = load_config(args.config)
    if args.runtime:
        config["runtime"] = {**config.get("runtime", {}), "type": args.runtime}
    if args.cluster_worker:
        client = ClusterWorkerClient(config)
        result = client.run_once(runtime_type=args.runtime)
        log_event(logger, "cluster_worker.once.complete", worker_id=config["worker"]["id"], status=result.get("status"), accepted=result.get("accepted"))
        return
    db = WorkerDB(config["worker"]["db_path"])
    try:
        daemon = WorkerDaemon(config, db)
        if args.loop:
            log_event(logger, "daemon.loop.start", worker_id=config["worker"]["id"], runtime=args.runtime or config.get("runtime", {}).get("type"))
            daemon.run_loop(runtime_type=args.runtime)
        else:
            receipt = daemon.run_once(runtime_type=args.runtime)
            log_event(
                logger,
                "daemon.once.complete",
                worker_id=config["worker"]["id"],
                runtime=args.runtime or config.get("runtime", {}).get("type"),
                receipt_id=receipt.get("receipt_id") if receipt else None,
            )
    finally:
        db.close()


def _job_for_verifier(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": job["job_id"],
        "input_tokens": job.get("input_tokens", 0),
        "output_tokens": job.get("expected_output_tokens", 0),
    }


def _job_for_challenge(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": job["job_id"],
        "input_tokens": job.get("input_tokens", 0),
        "output_tokens": job.get("expected_output_tokens", 0),
        "tokens": job.get("expected_output_tokens", 0),
        "challenge_response_hash": job.get("challenge_response_hash"),
    }


def _verification_failure(reason: str, job: dict[str, Any], receipt: dict[str, Any], metadata: dict[str, Any]) -> Any:
    from verifier import VerificationResult

    return VerificationResult(
        accepted=False,
        reason=reason,
        score=0.0,
        metadata={
            "job_id": job.get("job_id"),
            "worker_id": receipt.get("worker_id"),
            **metadata,
        },
    )


def _estimated_qi(job: dict[str, Any], result: Any, config: dict[str, Any]) -> float:
    inference_cfg = config.get("inference", {})
    fallback_rate = float(inference_cfg.get("estimated_qi_per_token", 0))
    input_rate = float(inference_cfg.get("estimated_qi_per_input_token", fallback_rate))
    output_rate = float(inference_cfg.get("estimated_qi_per_output_token", fallback_rate))
    return float(result.input_tokens) * input_rate + float(result.output_tokens) * output_rate


def _refresh_receipt_hash(receipt: dict[str, Any]) -> str:
    receipt.pop("receipt_hash", None)
    return compute_receipt_hash(receipt)


def receipt_from_runtime_result(config: dict[str, Any], worker_id: str, job: dict[str, Any], result: Any) -> dict[str, Any]:
    estimated_qi = _estimated_qi(job, result, config) if result.accepted else 0.0
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
        worker_id=worker_id,
        mode="inference",
        started_at=result.started_at,
        ended_at=result.ended_at,
        duration_seconds=max(result.duration_seconds, 0.001),
        average_watts=float(result.metadata.get("total_watts") or config["worker"].get("fallback_watts", 0)),
        output_type="tokens",
        output_amount=result.output_tokens,
        estimated_qi_owed=estimated_qi,
        metadata=metadata,
    ).to_dict()


def _redact_receipt_for_cluster(receipt: dict[str, Any]) -> dict[str, Any]:
    return redact_sensitive_fields(receipt)


if __name__ == "__main__":
    main()
