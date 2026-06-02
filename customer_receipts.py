from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from receipts import utc_now_iso


@dataclass(frozen=True)
class CustomerReceipt:
    customer_receipt_id: str
    job_id: str
    customer_id: str
    assigned_worker_id: str | None
    model: str
    prompt_hash: str
    quoted_price_qi: float
    final_price_qi: float
    status: str
    route_score: float | None
    verification_accepted: bool
    verification_reason: str
    worker_receipt_hash: str | None
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        receipt = {
            "customer_receipt_id": self.customer_receipt_id,
            "job_id": self.job_id,
            "customer_id": self.customer_id,
            "assigned_worker_id": self.assigned_worker_id,
            "model": self.model,
            "prompt_hash": self.prompt_hash,
            "quoted_price_qi": self.quoted_price_qi,
            "final_price_qi": self.final_price_qi,
            "status": self.status,
            "route_score": self.route_score,
            "verification_accepted": self.verification_accepted,
            "verification_reason": self.verification_reason,
            "worker_receipt_hash": self.worker_receipt_hash,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }
        receipt["customer_receipt_hash"] = compute_customer_receipt_hash(receipt)
        return receipt


def build_customer_receipt(
    customer_job: dict[str, Any],
    route_decision: Any,
    worker_receipt: dict[str, Any],
    verification_result: dict[str, Any],
) -> dict[str, Any]:
    metadata = dict(customer_job.get("metadata", {}))
    metadata.pop("prompt", None)
    metadata.pop("raw_prompt", None)
    quoted = float(customer_job.get("max_price_qi", 0))
    final = float(worker_receipt.get("estimated_qi_owed", 0)) if verification_result.get("accepted") else 0.0
    return CustomerReceipt(
        customer_receipt_id=str(uuid4()),
        job_id=customer_job["job_id"],
        customer_id=customer_job.get("customer_id") or "unknown-customer",
        assigned_worker_id=getattr(route_decision, "worker_id", customer_job.get("assigned_worker_id")),
        model=customer_job["model"],
        prompt_hash=customer_job.get("prompt_hash"),
        quoted_price_qi=quoted,
        final_price_qi=final,
        status=customer_job.get("status", "unknown"),
        route_score=getattr(route_decision, "score", customer_job.get("route_score")),
        verification_accepted=bool(verification_result.get("accepted")),
        verification_reason=verification_result.get("reason", ""),
        worker_receipt_hash=worker_receipt.get("receipt_hash"),
        created_at=utc_now_iso(),
        metadata=metadata,
    ).to_dict()


def compute_customer_receipt_hash(receipt: dict[str, Any]) -> str:
    payload = copy.deepcopy(receipt)
    payload.pop("customer_receipt_hash", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
