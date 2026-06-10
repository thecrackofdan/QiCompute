from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from challenges import create_challenge, expected_challenge_hash, verify_challenge_result
from committees import ACCEPTED, aggregate_committee_votes
from receipts import make_receipt, utc_now_iso
from verifier import verify_inference_receipt


@dataclass(frozen=True)
class VerificationBenchmarkReport:
    receipt_verification_ms: float
    challenge_verification_ms: float
    committee_verification_ms: float
    settlement_overhead_ms: float
    throughput_per_second: float
    percentage_overhead: float

    def to_dict(self) -> dict[str, float]:
        return {
            "receipt_verification_ms": self.receipt_verification_ms,
            "challenge_verification_ms": self.challenge_verification_ms,
            "committee_verification_ms": self.committee_verification_ms,
            "settlement_overhead_ms": self.settlement_overhead_ms,
            "throughput_per_second": self.throughput_per_second,
            "percentage_overhead": self.percentage_overhead,
        }


def run_verification_benchmarks(iterations: int = 100, inference_duration_ms: float = 1000.0) -> VerificationBenchmarkReport:
    count = max(int(iterations), 1)
    receipt = _receipt()
    job = {"id": "verification-benchmark-job", "input_tokens": 8, "output_tokens": 32}
    challenge = create_challenge(
        {"id": job["id"], "output_tokens": 32},
        "benchmark-worker",
        {"challenges": {"enabled": True, "challenge_rate": 1.0, "expected_tokens": 32}},
    )
    receipt["metadata"]["challenge_response_hash"] = expected_challenge_hash(job["id"], challenge["challenge_type"], 32)
    receipt["receipt_hash"] = _rehash(receipt)

    receipt_ms = _measure_ms(count, lambda: verify_inference_receipt(receipt, job, {}))
    challenge_ms = _measure_ms(count, lambda: verify_challenge_result(challenge, receipt))
    committee_ms = _measure_ms(
        count,
        lambda: aggregate_committee_votes(
            [
                {"vote": ACCEPTED},
                {"vote": ACCEPTED},
                {"vote": ACCEPTED},
            ],
            2,
        ),
    )
    settlement_ms = _measure_ms(count, lambda: _settlement_math(receipt))
    total_ms = receipt_ms + challenge_ms + committee_ms + settlement_ms
    throughput = 1000.0 / max(total_ms, 0.000001)
    percentage = total_ms / max(float(inference_duration_ms), 0.000001) * 100.0
    return VerificationBenchmarkReport(
        receipt_verification_ms=round(receipt_ms, 12),
        challenge_verification_ms=round(challenge_ms, 12),
        committee_verification_ms=round(committee_ms, 12),
        settlement_overhead_ms=round(settlement_ms, 12),
        throughput_per_second=round(throughput, 12),
        percentage_overhead=round(percentage, 12),
    )


def _measure_ms(iterations: int, fn: Any) -> float:
    started = time.perf_counter()
    for _ in range(iterations):
        fn()
    return (time.perf_counter() - started) * 1000.0 / iterations


def _receipt() -> dict[str, Any]:
    now = utc_now_iso()
    receipt = make_receipt(
        worker_id="benchmark-worker",
        mode="inference",
        started_at=now,
        ended_at=now,
        duration_seconds=1,
        average_watts=100,
        output_type="tokens",
        output_amount=32,
        estimated_qi_owed=0.01,
        metadata={"accepted": True, "job_id": "verification-benchmark-job", "input_tokens": 8, "output_tokens": 32},
    ).to_dict()
    return receipt


def _rehash(receipt: dict[str, Any]) -> str:
    from receipts import compute_receipt_hash

    receipt.pop("receipt_hash", None)
    return compute_receipt_hash(receipt)


def _settlement_math(receipt: dict[str, Any]) -> dict[str, float]:
    settled = float(receipt["estimated_qi_owed"])
    fee = round(settled * 0.025, 12)
    return {"settled": settled, "fee": fee, "worker_payout": round(settled - fee, 12)}
