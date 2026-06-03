from __future__ import annotations

import argparse
import json
import urllib.parse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from uuid import uuid4

import failures
from accounts import record_worker_rejected, refund_job_escrow, settle_job_escrow
from capabilities import verify_capability_claim
from db import WorkerDB
from enrollment import activate_worker_enrollment, get_active_worker_secret
from epochs import active_epoch
from privacy import redact_sensitive_fields
from receipts import compute_receipt_hash, utc_now_iso
from reputation import update_worker_reputation
from router import route_and_audit_inference_job
from treasury import record_refund, record_settlement
from transport import NONCE_HEADER, TIMESTAMP_HEADER, verify_request_signature
from verifier import VerificationResult, verify_inference_receipt
from worker import load_config


class ClusterController:
    def __init__(self, db: WorkerDB, config: dict[str, Any]):
        self.db = db
        self.config = config
        self.secret = config.get("cluster", {}).get("shared_secret", "dev-local-secret")

    def handle_heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        worker_id = payload.get("worker_id")
        if not worker_id:
            self._event("heartbeat", None, None, False, failures.AUTH_FAILED, {"reason": "missing worker_id"})
            return {"accepted": False, "failure_code": failures.AUTH_FAILED, "reason": "missing worker_id"}
        if not self.db.get_worker(worker_id):
            self.db.register_worker(_minimal_worker(worker_id, payload))
        telemetry = dict(payload.get("telemetry", {}))
        telemetry["last_seen_at"] = telemetry.get("last_seen_at") or utc_now_iso()
        self.db.update_worker_heartbeat(worker_id, telemetry)
        self._event("heartbeat", worker_id, None, True, None, {"telemetry": telemetry})
        return {"accepted": True, "worker_id": worker_id}

    def handle_capability(self, payload: dict[str, Any]) -> dict[str, Any]:
        worker = dict(payload.get("worker", {}))
        claim = dict(payload.get("capability_claim", {}))
        verification = verify_capability_claim(claim)
        worker_id = worker.get("worker_id") or claim.get("worker_id")
        if not verification.get("accepted"):
            self._event("capability", worker_id, None, False, failures.INVALID_CAPABILITY_CLAIM, verification)
            return {"accepted": False, "failure_code": failures.INVALID_CAPABILITY_CLAIM, "reason": verification["reason"]}
        worker.setdefault("worker_id", claim["worker_id"])
        worker.setdefault("operator", "cluster-worker")
        worker.setdefault("region", claim.get("region", "local"))
        worker.setdefault("public_key", "placeholder-public-key")
        worker.setdefault("endpoint", "cluster")
        worker.setdefault("hardware_profile", {"gpu_count": claim.get("gpu_count", 0), "gpu_names": claim.get("gpu_names", [])})
        worker.setdefault("supported_modes", ["inference", "mining"])
        worker.setdefault("supported_models", claim.get("supported_models", []))
        worker.setdefault("gpu_count", claim.get("gpu_count", 0))
        worker.setdefault("total_vram_gb", claim.get("total_vram_gb", 0))
        worker.setdefault("total_watts_capacity", claim.get("total_watts_capacity", 0))
        worker.setdefault("online", True)
        worker.setdefault("last_seen_at", utc_now_iso())
        worker.setdefault("metadata", {})
        worker["metadata"] = {**worker.get("metadata", {}), "capability_claim": claim, "capability_hash": claim.get("capability_hash")}
        self.db.register_worker(worker)
        if self.config.get("cluster", {}).get("allow_dev_shared_secret", False):
            activate_worker_enrollment(self.db, worker["worker_id"], self.config.get("cluster", {}).get("shared_secret", self.secret))
        self._event("capability", worker["worker_id"], None, True, None, {"capability_hash": claim.get("capability_hash")})
        return {"accepted": True, "worker_id": worker["worker_id"]}

    def handle_next_job(self, worker_id: str) -> dict[str, Any]:
        self.db.requeue_expired_leased_jobs(utc_now_iso())
        worker = self.db.get_worker(worker_id)
        if not worker or not worker.get("online"):
            self._event("job_next", worker_id, None, False, failures.WORKER_OFFLINE, {})
            return {"accepted": True, "job": None, "reason": "worker offline or unknown"}
        for job in self.db.list_queued_jobs():
            decision = route_and_audit_inference_job(self.db, {**job, "requires_gpu": True}, [worker])
            if decision.accepted and decision.worker_id:
                lease_seconds = int(self.config.get("cluster", {}).get("job_lease_seconds", 60))
                assigned = self.db.lease_customer_job(job["job_id"], worker_id, lease_seconds)
                self._event("job_assigned", worker_id, job["job_id"], True, None, {"route_score": decision.score, "lease_id": assigned.get("lease_id")})
                return {"accepted": True, "job": _job_payload_for_worker(assigned)}
        self._event("job_next", worker_id, None, True, None, {"job": None})
        return {"accepted": True, "job": None, "reason": "no eligible job"}

    def handle_receipt(self, payload: dict[str, Any]) -> dict[str, Any]:
        receipt = dict(payload.get("receipt", {}))
        job_id = receipt.get("metadata", {}).get("job_id") or payload.get("job_id")
        job = self.db.get_customer_job(job_id) if job_id else None
        if not receipt or not job:
            self._event("receipt", receipt.get("worker_id"), job_id, False, failures.VERIFICATION_FAILED, {"reason": "missing receipt or job"})
            return {"accepted": False, "failure_code": failures.VERIFICATION_FAILED, "reason": "missing receipt or job"}
        receipt["receipt_hash"] = receipt.get("receipt_hash") or compute_receipt_hash(receipt)
        if self.db.receipt_already_settled(receipt.get("receipt_hash"), receipt.get("receipt_id")):
            self._event("receipt_replay", receipt.get("worker_id"), job_id, False, failures.DUPLICATE_RECEIPT, {"receipt_hash": receipt.get("receipt_hash")})
            return {"accepted": False, "failure_code": failures.DUPLICATE_RECEIPT, "reason": "receipt already settled"}
        if self.db.stale_receipt_detected(job_id, receipt.get("receipt_hash")):
            self._event("stale_receipt", receipt.get("worker_id"), job_id, False, failures.STALE_RECEIPT, {"receipt_hash": receipt.get("receipt_hash")})
            return {"accepted": False, "failure_code": failures.STALE_RECEIPT, "reason": "stale receipt cannot settle"}
        if self.db.inference_job_was_paid(job["job_id"]):
            self._event("receipt", receipt.get("worker_id"), job_id, False, failures.DUPLICATE_JOB, {"reason": "duplicate receipt"})
            return {"accepted": False, "failure_code": failures.DUPLICATE_JOB, "reason": "job already settled"}
        if payload.get("lease_id") != job.get("lease_id"):
            self._event("receipt", receipt.get("worker_id"), job_id, False, failures.INVALID_LEASE, {"reason": "lease mismatch"})
            return {"accepted": False, "failure_code": failures.INVALID_LEASE, "reason": "lease mismatch"}
        if job.get("lease_expires_at") and job["lease_expires_at"] <= utc_now_iso():
            self.db.requeue_expired_leased_jobs(utc_now_iso())
            refund = refund_job_escrow(self.db, job["job_id"], failures.LEASE_EXPIRED)
            record_refund(self.db, refund_qi=refund.get("refund_qi", 0))
            self._event("receipt", receipt.get("worker_id"), job_id, False, failures.LEASE_EXPIRED, {"reason": "lease expired"})
            return {"accepted": False, "failure_code": failures.LEASE_EXPIRED, "reason": "lease expired"}
        verification = verify_inference_receipt(receipt, _job_for_verifier(job), self.config)
        receipt.setdefault("metadata", {})["verification"] = verification.to_dict()
        receipt["receipt_hash"] = _refresh_receipt_hash(receipt)
        self.db.insert_receipt(receipt)
        update_worker_reputation(self.db, worker_id=receipt["worker_id"], verification=verification.to_dict(), receipt=receipt)
        if job["status"] == "routed":
            self.db.update_customer_job_status(job["job_id"], "running", {"source": "cluster-controller"})
        if not verification.accepted:
            failure_code = verification.reason
            self.db.mark_customer_job_failure(job["job_id"], failure_code, "cluster receipt rejected")
            self.db.decrement_worker_load(receipt["worker_id"])
            refund = refund_job_escrow(self.db, job["job_id"], "disputed" if failure_code == failures.COMMITTEE_DISPUTED else failure_code)
            record_refund(self.db, refund_qi=refund.get("refund_qi", 0), disputed=failure_code == failures.COMMITTEE_DISPUTED)
            record_worker_rejected(self.db, receipt["worker_id"], receipt.get("estimated_qi_owed", 0), disputed=failure_code == failures.COMMITTEE_DISPUTED)
            self._event("receipt", receipt["worker_id"], job["job_id"], False, failure_code, verification.to_dict())
            return {"accepted": False, "failure_code": failure_code, "verification": verification.to_dict()}
        epoch = active_epoch(self.db)
        settlement = settle_job_escrow(
            self.db,
            job["job_id"],
            receipt["worker_id"],
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
            "worker_id": receipt["worker_id"],
            "event_type": "inference_job",
            "basis": "cluster_verified_runtime",
            "qi_amount": settlement["worker_payout_qi"],
            "created_at": utc_now_iso(),
            "source_id": receipt["receipt_id"],
            "epoch_id": epoch["epoch_id"],
            "metadata": {
                "job_id": job["job_id"],
                "verification_reason": verification.reason,
                "settled_qi": settlement["settled_qi"],
                "fee_qi": settlement["fee_qi"],
            },
        }
        self.db.insert_payout_event(payout_event)
        self.db.record_inference_job_paid(
            job_id=job["job_id"],
            worker_id=receipt["worker_id"],
            receipt_id=receipt["receipt_id"],
            accepted_at=payout_event["created_at"],
            payout_event_id=payout_event["event_id"],
        )
        self.db.update_customer_job_status(job["job_id"], "completed", {"receipt_id": receipt["receipt_id"]})
        self.db.decrement_worker_load(receipt["worker_id"])
        self._event("receipt", receipt["worker_id"], job["job_id"], True, None, {"epoch_id": epoch["epoch_id"]})
        return {"accepted": True, "job_id": job["job_id"], "receipt_id": receipt["receipt_id"], "epoch_id": epoch["epoch_id"]}

    def handle_challenge_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = dict(payload.get("challenge_result", {}))
        if not result:
            self._event("challenge_result", payload.get("worker_id"), payload.get("job_id"), False, failures.CHALLENGE_FAILED, {})
            return {"accepted": False, "failure_code": failures.CHALLENGE_FAILED}
        self.db.record_challenge_result(result)
        self._event("challenge_result", result.get("worker_id"), result.get("job_id"), bool(result.get("accepted")), None if result.get("accepted") else result.get("reason"), {})
        return {"accepted": True}

    def verify_headers(self, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        worker_id = payload.get("worker_id")
        if not worker_id:
            return {"accepted": False, "failure_code": failures.AUTH_FAILED, "reason": "missing worker_id"}
        secret = self._secret_for_worker(worker_id)
        if not secret:
            return {"accepted": False, "failure_code": failures.AUTH_FAILED, "reason": "worker is not actively enrolled"}
        normalized = {key.lower(): value for key, value in headers.items()}
        nonce = normalized.get(NONCE_HEADER.lower())
        timestamp = normalized.get(TIMESTAMP_HEADER.lower())
        if nonce and self.db.transport_nonce_seen(nonce):
            return {"accepted": False, "failure_code": failures.INVALID_NONCE, "reason": "nonce already used"}
        result = verify_request_signature(
            payload,
            headers,
            secret,
            max_age_seconds=int(self.config.get("cluster", {}).get("request_timeout_seconds", 5)) + 300,
            nonce_cache=set(),
        )
        if result.get("accepted") and nonce:
            self.db.record_transport_nonce(
                nonce,
                created_at=utc_now_iso(),
                expires_at=_nonce_expires_at(timestamp, int(self.config.get("cluster", {}).get("request_timeout_seconds", 5)) + 300),
                source_worker_id=worker_id,
                metadata={"source": "controller"},
            )
        return result

    def _secret_for_worker(self, worker_id: str) -> str | None:
        cluster_cfg = self.config.get("cluster", {})
        candidates = []
        if isinstance(cluster_cfg.get("worker_secrets"), dict):
            candidates.append(cluster_cfg["worker_secrets"].get(worker_id))
        if cluster_cfg.get("allow_dev_shared_secret", False):
            candidates.append(cluster_cfg.get("shared_secret", self.secret))
        for candidate in [secret for secret in candidates if secret]:
            if get_active_worker_secret(self.db, worker_id, candidate):
                return candidate
        return None

    def _event(self, event_type: str, worker_id: str | None, job_id: str | None, accepted: bool, failure_code: str | None, metadata: dict[str, Any]) -> None:
        self.db.insert_cluster_event(
            {
                "event_id": str(uuid4()),
                "event_type": event_type,
                "worker_id": worker_id,
                "job_id": job_id,
                "created_at": utc_now_iso(),
                "accepted": accepted,
                "failure_code": failure_code,
                "metadata": metadata,
            }
        )


def run_server(host: str, port: int, config: dict[str, Any], db: WorkerDB) -> None:
    controller = ClusterController(db, config)
    server = ThreadingHTTPServer((host, port), _handler(controller))
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="QiCompute local LAN controller")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    config = load_config(args.config)
    db = WorkerDB(config["worker"]["db_path"])
    try:
        run_server(args.host, args.port, config, db)
    finally:
        db.close()


def _handler(controller: ClusterController) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            payload = self._read_json()
            auth = controller.verify_headers(payload, dict(self.headers))
            if not auth["accepted"]:
                controller._event("auth_failure", payload.get("worker_id"), payload.get("job_id"), False, auth["failure_code"], auth)
                self._json({"accepted": False, "failure_code": auth["failure_code"], "reason": auth["reason"]}, status=401)
                return
            if self.path == "/heartbeat":
                self._json(controller.handle_heartbeat(payload))
            elif self.path == "/capability":
                self._json(controller.handle_capability(payload))
            elif self.path == "/receipt":
                self._json(controller.handle_receipt(payload))
            elif self.path == "/challenge-result":
                self._json(controller.handle_challenge_result(payload))
            else:
                self._json({"accepted": False, "failure_code": failures.TRANSPORT_ERROR, "reason": "not found"}, status=404)

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/job/next":
                self._json({"accepted": False, "failure_code": failures.TRANSPORT_ERROR, "reason": "not found"}, status=404)
                return
            query = urllib.parse.parse_qs(parsed.query)
            worker_id = query.get("worker_id", [""])[0]
            payload = {"worker_id": worker_id}
            auth = controller.verify_headers(payload, dict(self.headers))
            if not auth["accepted"]:
                controller._event("auth_failure", worker_id, None, False, auth["failure_code"], auth)
                self._json({"accepted": False, "failure_code": auth["failure_code"], "reason": auth["reason"]}, status=401)
                return
            self._json(controller.handle_next_job(worker_id))

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def _json(self, payload: dict[str, Any], status: int = 200) -> None:
            body = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def _minimal_worker(worker_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "worker_id": worker_id,
        "operator": payload.get("operator", "cluster-worker"),
        "region": payload.get("region", "local"),
        "public_key": payload.get("public_key", "placeholder-public-key"),
        "endpoint": payload.get("endpoint", "cluster"),
        "hardware_profile": payload.get("hardware_profile", {}),
        "supported_modes": payload.get("supported_modes", ["inference", "mining"]),
        "supported_models": payload.get("supported_models", ["llama-3.1-8b"]),
        "gpu_count": payload.get("gpu_count", 0),
        "total_vram_gb": payload.get("total_vram_gb", 0),
        "total_watts_capacity": payload.get("total_watts_capacity", 0),
        "online": True,
        "last_seen_at": utc_now_iso(),
        "metadata": {"source": "cluster-heartbeat"},
    }


def _job_payload_for_worker(job: dict[str, Any]) -> dict[str, Any]:
    metadata = redact_sensitive_fields(job.get("metadata", {}))
    payload = {**job, "metadata": metadata}
    payload.pop("payload_key", None)
    return redact_sensitive_fields(payload)


def _job_for_verifier(job: dict[str, Any]) -> dict[str, Any]:
    return {"id": job["job_id"], "input_tokens": job.get("input_tokens", 0), "output_tokens": job.get("expected_output_tokens", 0)}


def _refresh_receipt_hash(receipt: dict[str, Any]) -> str:
    receipt.pop("receipt_hash", None)
    return compute_receipt_hash(receipt)


def _nonce_expires_at(timestamp: str | None, max_age_seconds: int) -> str:
    try:
        base = datetime.fromtimestamp(int(timestamp or "0"), tz=timezone.utc)
    except ValueError:
        base = datetime.now(timezone.utc)
    return (base + timedelta(seconds=max_age_seconds)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    main()
