from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid5, NAMESPACE_URL

from privacy import redact_sensitive_fields


def build_settlement_invoice(
    *,
    invoice_type: str,
    job: dict[str, Any] | None,
    epoch: dict[str, Any] | None,
    receipt: dict[str, Any] | None,
    escrow: dict[str, Any] | None,
    committee_outcome: str | None = None,
    challenge_outcome: str | None = None,
) -> dict[str, Any]:
    job_id = job.get("job_id") if job else None
    epoch_id = epoch.get("epoch_id") if epoch else None
    receipt_hash = receipt.get("receipt_hash") if receipt else None
    invoice_id = str(uuid5(NAMESPACE_URL, f"qicompute:{invoice_type}:{epoch_id}:{job_id}:{receipt_hash}"))
    invoice = {
        "invoice_id": invoice_id,
        "invoice_type": invoice_type,
        "job_id": job_id,
        "epoch_id": epoch_id,
        "customer_id": job.get("customer_id") if job else None,
        "worker_id": receipt.get("worker_id") if receipt else job.get("assigned_worker_id") if job else None,
        "estimated_qi": float(receipt.get("estimated_qi_owed", 0)) if receipt else float(job.get("max_price_qi", 0) if job else 0),
        "settled_qi": float(escrow.get("settled_qi", 0)) if escrow else 0.0,
        "fee_qi": float(escrow.get("fee_qi", 0)) if escrow else 0.0,
        "worker_payout_qi": float(escrow.get("worker_payout_qi", 0)) if escrow else 0.0,
        "refund_qi": float(escrow.get("refunded_qi", 0)) if escrow else 0.0,
        "status": escrow.get("status") if escrow else job.get("status") if job else "unknown",
        "created_at": (receipt.get("ended_at") if receipt else None)
        or (epoch.get("ended_at") if epoch else None)
        or (job.get("updated_at") if job else None)
        or (job.get("created_at") if job else None),
        "receipt_hashes": [receipt_hash] if receipt_hash else [],
        "committee_outcome": committee_outcome,
        "challenge_outcome": challenge_outcome,
        "metadata": {},
    }
    redacted = redact_sensitive_fields(invoice)
    redacted["invoice_hash"] = compute_invoice_hash(redacted)
    return redacted


def compute_invoice_hash(invoice: dict[str, Any]) -> str:
    payload = {key: value for key, value in redact_sensitive_fields(invoice).items() if key != "invoice_hash"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
