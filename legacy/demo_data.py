from __future__ import annotations

import hashlib
from typing import Any

from privacy import make_private_job_payload
from receipts import utc_now_iso


DEMO_CUSTOMER_ID = "demo-customer-001"
DEMO_WORKER_ID = "demo-worker-local"
DEMO_MODEL = "llama-3.1-8b"


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def demo_prompt(mode: str) -> str:
    prompts = {
        "honest": "Summarize useful compute settlement in one short sentence.",
        "flaky": "Explain why runtime availability matters for private inference.",
        "malicious": "Return a short answer for a verification challenge.",
    }
    return prompts.get(mode, prompts["honest"])


def demo_job(mode: str) -> dict[str, Any]:
    prompt = demo_prompt(mode)
    private_payload = make_private_job_payload(prompt, {"demo_mode": mode}, None)
    return {
        "job_id": f"demo-job-{mode}",
        "customer_id": DEMO_CUSTOMER_ID,
        "model": DEMO_MODEL,
        "prompt_hash": prompt_hash(prompt),
        "encrypted_payload": private_payload["encrypted_payload"],
        "payload_nonce": private_payload["payload_nonce"],
        "payload_hash": private_payload["payload_hash"],
        "privacy_mode": private_payload["privacy_mode"],
        "payload_key": private_payload["payload_key"],
        "input_tokens": float(len(prompt.split())),
        "expected_output_tokens": 32.0,
        "privacy_level": "verified",
        "max_price_qi": 0.01,
        "status": "queued",
        "created_at": utc_now_iso(),
        "expires_at": "9999-01-01T00:00:00+00:00",
        "metadata": {"demo_mode": mode},
    }


def demo_workers(config: dict[str, Any]) -> list[dict[str, Any]]:
    worker_cfg = config["worker"]
    hardware = worker_cfg.get("hardware_profile", {})
    base = {
        "operator": "demo-operator",
        "region": worker_cfg.get("region", "local"),
        "public_key": "placeholder-demo-key",
        "endpoint": "local",
        "hardware_profile": hardware,
        "supported_modes": ["inference", "mining"],
        "supported_models": worker_cfg.get("supported_models", [DEMO_MODEL]),
        "gpu_count": hardware.get("gpu_count", 1),
        "total_vram_gb": hardware.get("total_vram_gb", 24),
        "total_watts_capacity": hardware.get("total_watts_capacity", worker_cfg.get("fallback_watts", 250)),
        "online": True,
        "last_seen_at": utc_now_iso(),
        "success_count": 0,
        "failure_count": 0,
        "average_latency_ms": 0,
        "average_energy_per_token": 0,
        "current_jobs": 0,
        "max_concurrent_jobs": 1,
        "load_percent": 0,
        "last_heartbeat_at": utc_now_iso(),
    }
    workers = []
    for worker_id, reputation in [
        (worker_cfg["id"], 50),
        ("demo-verifier-a", 80),
        ("demo-verifier-b", 75),
        ("demo-verifier-c", 70),
    ]:
        workers.append({**base, "worker_id": worker_id, "reputation_score": reputation, "metadata": {"demo": True}})
    return workers
