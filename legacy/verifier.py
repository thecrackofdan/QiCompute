from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import failures
from receipts import verify_receipt_hash


@dataclass(frozen=True)
class VerificationResult:
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


def verify_inference_receipt(
    receipt: dict[str, Any],
    job: dict[str, Any],
    config: dict[str, Any],
) -> VerificationResult:
    checks = [
        ("receipt mode must be inference", receipt.get("mode") == "inference"),
        ("job id is required", bool(job.get("id"))),
        ("output token count must be non-negative", _output_tokens(receipt, job) >= 0),
        ("input token count must be non-negative", _input_tokens(receipt, job) >= 0),
        ("duration must be positive", float(receipt.get("duration_seconds", 0)) > 0),
        ("energy_joules must be positive", float(receipt.get("energy_joules", 0)) > 0),
        ("accepted status must be explicit", isinstance(_accepted(receipt), bool)),
        ("worker_id is required", bool(receipt.get("worker_id"))),
        ("receipt_id is required", bool(receipt.get("receipt_id"))),
        ("receipt hash must verify", verify_receipt_hash(receipt)),
    ]
    failed = [reason for reason, ok in checks if not ok]
    if failed:
        return VerificationResult(
            accepted=False,
            reason=failures.VERIFICATION_FAILED,
            score=0.0,
            metadata={
                "job_id": job.get("id"),
                "worker_id": receipt.get("worker_id"),
                "reason_detail": "; ".join(failed),
                "failed_checks": failed,
            },
        )

    return VerificationResult(
        accepted=True,
        reason="receipt accepted",
        score=1.0,
        metadata={
            "job_id": job["id"],
            "worker_id": receipt["worker_id"],
            "input_tokens": _input_tokens(receipt, job),
            "output_tokens": _output_tokens(receipt, job),
        },
    )


def _accepted(receipt: dict[str, Any]) -> Any:
    return receipt.get("metadata", {}).get("accepted")


def _input_tokens(receipt: dict[str, Any], job: dict[str, Any]) -> float:
    value = receipt.get("metadata", {}).get("input_tokens", job.get("input_tokens", 0))
    return float(value)


def _output_tokens(receipt: dict[str, Any], job: dict[str, Any]) -> float:
    value = receipt.get("metadata", {}).get(
        "output_tokens",
        job.get("output_tokens", job.get("tokens", receipt.get("output", {}).get("amount", 0))),
    )
    return float(value)
