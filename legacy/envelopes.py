from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from receipts import utc_now_iso
import failures


@dataclass(frozen=True)
class JobEnvelope:
    envelope_id: str
    job_id: str
    customer_id: str
    model: str
    prompt_hash: str
    input_tokens: float
    expected_output_tokens: float
    privacy_level: str
    max_price_qi: float
    region_preference: str | None
    created_at: str
    expires_at: str
    nonce: str
    signature_placeholder: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        envelope = {
            "envelope_id": self.envelope_id,
            "job_id": self.job_id,
            "customer_id": self.customer_id,
            "model": self.model,
            "prompt_hash": self.prompt_hash,
            "input_tokens": self.input_tokens,
            "expected_output_tokens": self.expected_output_tokens,
            "privacy_level": self.privacy_level,
            "max_price_qi": self.max_price_qi,
            "region_preference": self.region_preference,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "nonce": self.nonce,
            "signature_placeholder": self.signature_placeholder,
            "metadata": self.metadata,
        }
        envelope["envelope_hash"] = compute_envelope_hash(envelope)
        return envelope


def make_job_envelope(
    *,
    job_id: str,
    customer_id: str,
    model: str,
    prompt_hash: str,
    input_tokens: float,
    expected_output_tokens: float,
    privacy_level: str,
    max_price_qi: float,
    region_preference: str | None = None,
    expires_at: str = "9999-12-31T23:59:59+00:00",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    safe_metadata = dict(metadata or {})
    safe_metadata.pop("prompt", None)
    safe_metadata.pop("raw_prompt", None)
    return JobEnvelope(
        envelope_id=str(uuid4()),
        job_id=job_id,
        customer_id=customer_id,
        model=model,
        prompt_hash=prompt_hash,
        input_tokens=input_tokens,
        expected_output_tokens=expected_output_tokens,
        privacy_level=privacy_level,
        max_price_qi=max_price_qi,
        region_preference=region_preference,
        created_at=utc_now_iso(),
        expires_at=expires_at,
        nonce=str(uuid4()),
        signature_placeholder="placeholder-signature",
        metadata=safe_metadata,
    ).to_dict()


def compute_envelope_hash(envelope: dict[str, Any]) -> str:
    payload = copy.deepcopy(envelope)
    payload.pop("envelope_hash", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_job_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    required = [
        "envelope_id",
        "job_id",
        "customer_id",
        "model",
        "prompt_hash",
        "created_at",
        "expires_at",
        "nonce",
        "signature_placeholder",
    ]
    missing = [field for field in required if not envelope.get(field)]
    if missing:
        return {"accepted": False, "reason": failures.INVALID_ENVELOPE, "metadata": {"missing": missing}}
    if str(envelope.get("expires_at", "")) <= str(envelope.get("created_at", "")):
        return {"accepted": False, "reason": failures.INVALID_ENVELOPE, "metadata": {"reason_detail": "expires_at is invalid"}}
    if envelope.get("envelope_hash") and envelope["envelope_hash"] != compute_envelope_hash(envelope):
        return {"accepted": False, "reason": failures.INVALID_ENVELOPE, "metadata": {"reason_detail": "envelope hash mismatch"}}
    return {"accepted": True, "reason": "envelope accepted", "metadata": {"job_id": envelope["job_id"]}}
