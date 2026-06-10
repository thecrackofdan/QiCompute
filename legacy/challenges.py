from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import failures


DETERMINISTIC_PROMPT = "deterministic_prompt"
KNOWN_OUTPUT = "known_output"
TIMING_CHALLENGE = "timing_challenge"
DUPLICATE_EXECUTION = "duplicate_execution"
PARTIAL_OUTPUT_VERIFICATION = "partial_output_verification"

CHALLENGE_TYPES = {
    DETERMINISTIC_PROMPT,
    KNOWN_OUTPUT,
    TIMING_CHALLENGE,
    DUPLICATE_EXECUTION,
    PARTIAL_OUTPUT_VERIFICATION,
}


@dataclass(frozen=True)
class ChallengeVerification:
    accepted: bool
    reason: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "reason": self.reason,
            "score": self.score,
            "metadata": self.metadata,
        }


def should_attach_challenge(job: dict[str, Any], config: dict[str, Any]) -> bool:
    cfg = (config or {}).get("challenges", {})
    if not cfg.get("enabled", False):
        return False
    rate = float(cfg.get("challenge_rate", cfg.get("percentage", 0)))
    if rate <= 0:
        return False
    if rate >= 1:
        return True
    job_id = _job_id(job)
    if not job_id:
        return False
    bucket = int(hashlib.sha256(job_id.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
    return bucket < rate


def create_challenge(job: dict[str, Any], worker_id: str, config: dict[str, Any]) -> dict[str, Any]:
    cfg = (config or {}).get("challenges", {})
    challenge_type = cfg.get("challenge_type", DETERMINISTIC_PROMPT)
    if challenge_type not in CHALLENGE_TYPES:
        raise ValueError(f"Unsupported challenge type: {challenge_type}")
    created_at = _now()
    ttl_seconds = float(cfg.get("ttl_seconds", 300))
    expected_tokens = float(
        job.get(
            "challenge_expected_tokens",
            job.get("output_tokens", job.get("tokens", cfg.get("expected_tokens", 0))),
        )
    )
    expected_hash = job.get("challenge_expected_hash") or expected_challenge_hash(
        _job_id(job),
        challenge_type,
        expected_tokens,
    )
    return {
        "challenge_id": str(uuid4()),
        "job_id": _job_id(job),
        "challenge_type": challenge_type,
        "expected_hash": expected_hash,
        "expected_tokens": expected_tokens,
        "created_at": created_at,
        "expires_at": _add_seconds(created_at, ttl_seconds),
        "assigned_worker_id": worker_id,
        "verifier_worker_id": cfg.get("verifier_worker_id"),
        "metadata": {
            "policy": "local_deterministic",
            "challenge_rate": float(cfg.get("challenge_rate", cfg.get("percentage", 0))),
        },
    }


def expected_challenge_hash(job_id: str, challenge_type: str, expected_tokens: float) -> str:
    payload = f"{job_id}:{challenge_type}:{float(expected_tokens):.8f}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_challenge_result(challenge: dict[str, Any], receipt: dict[str, Any]) -> ChallengeVerification:
    now = _now()
    if challenge.get("expires_at") and str(challenge["expires_at"]) <= now:
        return ChallengeVerification(
            accepted=False,
            reason=failures.CHALLENGE_EXPIRED,
            score=0.0,
            metadata={"challenge_id": challenge.get("challenge_id"), "expired_at": challenge.get("expires_at")},
        )

    metadata = receipt.get("metadata", {})
    response_hash = metadata.get("challenge_response_hash")
    expected_hash = challenge.get("expected_hash")
    output_tokens = float(metadata.get("output_tokens", receipt.get("output", {}).get("amount", 0)) or 0)
    expected_tokens = float(challenge.get("expected_tokens", 0) or 0)

    failed_checks = []
    if receipt.get("mode") != "inference":
        failed_checks.append("receipt mode must be inference")
    if metadata.get("job_id") != challenge.get("job_id"):
        failed_checks.append("receipt job_id must match challenge")
    if response_hash != expected_hash:
        failed_checks.append("challenge response hash mismatch")
    if output_tokens < expected_tokens:
        failed_checks.append("output tokens below challenge expectation")

    challenge_type = challenge.get("challenge_type")
    if challenge_type == TIMING_CHALLENGE:
        max_duration = float(challenge.get("metadata", {}).get("max_duration_seconds", 60))
        if float(receipt.get("duration_seconds", 0)) > max_duration:
            failed_checks.append("duration exceeds timing challenge")

    if failed_checks:
        return ChallengeVerification(
            accepted=False,
            reason=failures.CHALLENGE_FAILED,
            score=0.0,
            metadata={
                "challenge_id": challenge.get("challenge_id"),
                "failed_checks": failed_checks,
                "reason_detail": "; ".join(failed_checks),
            },
        )

    return ChallengeVerification(
        accepted=True,
        reason="challenge accepted",
        score=1.0,
        metadata={
            "challenge_id": challenge.get("challenge_id"),
            "challenge_type": challenge_type,
            "job_id": challenge.get("job_id"),
        },
    )


def build_challenge_result(
    challenge: dict[str, Any],
    receipt: dict[str, Any],
    verification: ChallengeVerification,
) -> dict[str, Any]:
    return {
        "result_id": str(uuid4()),
        "challenge_id": challenge["challenge_id"],
        "job_id": challenge["job_id"],
        "receipt_id": receipt.get("receipt_id"),
        "worker_id": receipt.get("worker_id"),
        "accepted": verification.accepted,
        "reason": verification.reason,
        "score": verification.score,
        "created_at": _now(),
        "metadata": verification.metadata,
    }


def record_challenge_result(result: dict[str, Any]) -> dict[str, Any]:
    return result


def _job_id(job: dict[str, Any]) -> str:
    return str(job.get("id") or job.get("job_id") or "")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _add_seconds(timestamp: str, seconds: float) -> str:
    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return (dt + timedelta(seconds=seconds)).isoformat()
