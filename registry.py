from __future__ import annotations

from typing import Any

from db import WorkerDB
from receipts import utc_now_iso


def worker_from_config(config: dict[str, Any]) -> dict[str, Any]:
    worker_cfg = config["worker"]
    hardware = worker_cfg.get("hardware_profile", {})
    return {
        "worker_id": worker_cfg["id"],
        "operator": worker_cfg.get("operator"),
        "region": worker_cfg.get("region"),
        "public_key": worker_cfg.get("public_key"),
        "endpoint": worker_cfg.get("endpoint", "local"),
        "hardware_profile": hardware,
        "supported_modes": worker_cfg.get("supported_modes", ["inference", "mining"]),
        "supported_models": worker_cfg.get("supported_models", ["llama-3.1-8b"]),
        "gpu_count": hardware.get("gpu_count") or 0,
        "total_vram_gb": hardware.get("total_vram_gb") or 0,
        "total_watts_capacity": hardware.get("total_watts_capacity") or worker_cfg.get("fallback_watts", 0),
        "online": True,
        "last_seen_at": utc_now_iso(),
        "reputation_score": worker_cfg.get("reputation_score", 50),
        "success_count": 0,
        "failure_count": 0,
        "average_latency_ms": 0,
        "average_energy_per_token": 0,
        "metadata": {"source": "config"},
    }


def register_local_worker(db: WorkerDB, config: dict[str, Any]) -> dict[str, Any]:
    worker = worker_from_config(config)
    db.register_worker(worker)
    return worker


def heartbeat_local_worker(db: WorkerDB, worker_id: str, telemetry: dict[str, Any] | None = None) -> None:
    payload = dict(telemetry or {})
    payload["last_seen_at"] = payload.get("last_seen_at") or utc_now_iso()
    db.update_worker_heartbeat(worker_id, payload)
