from __future__ import annotations

from typing import Any
from datetime import datetime

from db import WorkerDB


def update_worker_reputation(
    db: WorkerDB,
    *,
    worker_id: str,
    verification: dict[str, Any],
    receipt: dict[str, Any],
    duplicate_job: bool = False,
) -> dict[str, Any] | None:
    if duplicate_job:
        return db.get_worker(worker_id)
    worker = db.get_worker(worker_id)
    if not worker:
        return None

    accepted = bool(verification.get("accepted"))
    reason = verification.get("reason", "")
    reputation = float(worker["reputation_score"])
    success_count = int(worker["success_count"])
    failure_count = int(worker["failure_count"])

    if accepted:
        reputation += 1
        success_count += 1
    elif "verification" in reason or "receipt" in reason:
        reputation -= 5 + _failure_streak_penalty(worker)
        failure_count += 1
    else:
        reputation -= 3 + _failure_streak_penalty(worker)
        failure_count += 1

    reputation = min(100.0, max(0.0, reputation))
    latency_ms = float(receipt.get("duration_seconds", 0)) * 1000
    tokens = _receipt_token_count(receipt)
    energy_per_token = float(receipt.get("energy_joules", 0)) / tokens if tokens else 0.0
    average_latency_ms = _updated_average(worker["average_latency_ms"], worker["success_count"] + worker["failure_count"], latency_ms)
    average_energy_per_token = _updated_average(
        worker["average_energy_per_token"],
        worker["success_count"] + worker["failure_count"],
        energy_per_token,
    )
    stats = {
        "reputation_score": reputation,
        "success_count": success_count,
        "failure_count": failure_count,
        "average_latency_ms": average_latency_ms,
        "average_energy_per_token": average_energy_per_token,
    }
    db.update_worker_reputation_stats(worker_id, stats)
    return db.get_worker(worker_id)


def _updated_average(current: float, count: int, value: float) -> float:
    return value if count <= 0 else (float(current) * count + value) / (count + 1)


def _receipt_token_count(receipt: dict[str, Any]) -> float:
    metadata = receipt.get("metadata", {})
    return max(float(metadata.get("input_tokens", 0)) + float(metadata.get("output_tokens", 0)), 0.0)


def apply_reputation_decay(
    db: WorkerDB,
    *,
    worker_id: str,
    now: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    worker = db.get_worker(worker_id)
    if not worker:
        return None
    cfg = (config or {}).get("reputation", {})
    decay_per_day = float(cfg.get("decay_per_day", 0.25))
    offline_penalty = float(cfg.get("offline_penalty", 2))
    reputation = float(worker["reputation_score"])
    days = _days_between(worker.get("last_seen_at"), now)
    reputation -= days * decay_per_day
    if not worker.get("online"):
        reputation -= offline_penalty
    reputation = min(100.0, max(0.0, reputation))
    db.update_worker_reputation_stats(
        worker_id,
        {
            "reputation_score": reputation,
            "success_count": worker["success_count"],
            "failure_count": worker["failure_count"],
            "average_latency_ms": worker["average_latency_ms"],
            "average_energy_per_token": worker["average_energy_per_token"],
        },
    )
    return db.get_worker(worker_id)


def _failure_streak_penalty(worker: dict[str, Any]) -> float:
    failures = int(worker.get("failure_count", 0))
    return min(10.0, max(0, failures - 1) * 1.5)


def _days_between(start: str | None, end: str) -> float:
    if not start:
        return 0.0
    try:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    return max(0.0, (end_dt - start_dt).total_seconds() / 86400)
