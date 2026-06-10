from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from receipts import utc_now_iso
import failures


@dataclass(frozen=True)
class CapabilityClaim:
    worker_id: str
    supported_models: list[str]
    gpu_count: int
    gpu_names: list[str]
    total_vram_gb: float
    total_watts_capacity: float
    max_concurrent_jobs: int
    region: str
    privacy_features: list[str]
    benchmark_score: float
    updated_at: str
    signature_placeholder: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        claim = {
            "worker_id": self.worker_id,
            "supported_models": self.supported_models,
            "gpu_count": self.gpu_count,
            "gpu_names": self.gpu_names,
            "total_vram_gb": self.total_vram_gb,
            "total_watts_capacity": self.total_watts_capacity,
            "max_concurrent_jobs": self.max_concurrent_jobs,
            "region": self.region,
            "privacy_features": self.privacy_features,
            "benchmark_score": self.benchmark_score,
            "updated_at": self.updated_at,
            "signature_placeholder": self.signature_placeholder,
            "metadata": self.metadata,
        }
        claim["capability_hash"] = compute_capability_hash(claim)
        return claim


def make_capability_claim(worker: dict[str, Any]) -> dict[str, Any]:
    hardware = worker.get("hardware_profile", {})
    return CapabilityClaim(
        worker_id=worker.get("worker_id") or worker.get("id"),
        supported_models=list(worker.get("supported_models", [])),
        gpu_count=int(worker.get("gpu_count", hardware.get("gpu_count", 0)) or 0),
        gpu_names=list(hardware.get("gpu_names", [])),
        total_vram_gb=float(worker.get("total_vram_gb", hardware.get("total_vram_gb", 0)) or 0),
        total_watts_capacity=float(worker.get("total_watts_capacity", hardware.get("total_watts_capacity", 0)) or 0),
        max_concurrent_jobs=int(worker.get("max_concurrent_jobs", 1)),
        region=worker.get("region") or "unknown",
        privacy_features=list(worker.get("privacy_features", ["prompt_hash_only"])),
        benchmark_score=float(worker.get("benchmark_score", 0)),
        updated_at=utc_now_iso(),
        signature_placeholder=worker.get("signature_placeholder", "placeholder-signature"),
        metadata=dict(worker.get("metadata", {})),
    ).to_dict()


def compute_capability_hash(claim: dict[str, Any]) -> str:
    payload = copy.deepcopy(claim)
    payload.pop("capability_hash", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_capability_claim(claim: dict[str, Any]) -> dict[str, Any]:
    missing = []
    if not claim.get("worker_id"):
        missing.append("worker_id")
    if not claim.get("supported_models"):
        missing.append("supported_models")
    if not claim.get("signature_placeholder"):
        missing.append("signature_placeholder")
    if missing:
        return {"accepted": False, "reason": failures.INVALID_CAPABILITY_CLAIM, "metadata": {"missing": missing}}
    if claim.get("capability_hash") and claim["capability_hash"] != compute_capability_hash(claim):
        return {
            "accepted": False,
            "reason": failures.INVALID_CAPABILITY_CLAIM,
            "metadata": {"reason_detail": "capability hash mismatch"},
        }
    return {"accepted": True, "reason": "capability claim accepted", "metadata": {"worker_id": claim["worker_id"]}}
