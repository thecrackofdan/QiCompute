from __future__ import annotations

from typing import Any

from capabilities import make_capability_claim
from receipts import make_receipt, utc_now_iso


HONEST = "honest"
FLAKY = "flaky"
SLOW = "slow"
MALICIOUS_RECEIPT = "malicious_receipt"
FAKE_CAPABILITY = "fake_capability"
DUPLICATE_SUBMITTER = "duplicate_submitter"


def simulate_worker_receipt(worker_id: str, job: dict[str, Any], behavior: str, *, attempt: int = 0) -> dict[str, Any]:
    accepted = behavior not in {FLAKY, MALICIOUS_RECEIPT}
    duration = 10 if behavior == SLOW else 1
    if behavior == FLAKY and attempt % 2 == 0:
        accepted = False
    receipt = make_receipt(
        worker_id=worker_id,
        mode="inference",
        started_at=utc_now_iso(),
        ended_at=utc_now_iso(),
        duration_seconds=duration,
        average_watts=250,
        output_type="tokens",
        output_amount=job.get("expected_output_tokens", 100),
        estimated_qi_owed=0.0001 if accepted else 0,
        metadata={
            "job_id": job["job_id"],
            "accepted": accepted,
            "input_tokens": job.get("input_tokens", 0),
            "output_tokens": job.get("expected_output_tokens", 0),
            "behavior": behavior,
        },
    ).to_dict()
    if behavior == MALICIOUS_RECEIPT:
        receipt["output"]["amount"] += 999
    return receipt


def simulate_capability_claim(worker: dict[str, Any], behavior: str) -> dict[str, Any]:
    claim = make_capability_claim(worker)
    if behavior == FAKE_CAPABILITY:
        claim["total_vram_gb"] = 9999
    return claim


def duplicate_job(job: dict[str, Any]) -> dict[str, Any]:
    clone = dict(job)
    clone["metadata"] = dict(job.get("metadata", {}))
    clone["metadata"]["adversary"] = DUPLICATE_SUBMITTER
    return clone
