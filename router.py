from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RouteDecision:
    accepted: bool
    worker_id: str | None
    score: float
    reason: str
    alternatives: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "worker_id": self.worker_id,
            "score": self.score,
            "reason": self.reason,
            "alternatives": self.alternatives,
        }


def route_inference_job(job: dict[str, Any], workers: list[dict[str, Any]]) -> RouteDecision:
    eligible = []
    for worker in workers:
        if not worker.get("online"):
            continue
        if job["model"] not in worker.get("supported_models", []):
            continue
        if job.get("requires_gpu", True) and float(worker.get("gpu_count", 0)) <= 0:
            continue
        score = _score_worker(job, worker)
        eligible.append({"worker_id": worker["worker_id"], "score": score, "worker": worker})

    if not eligible:
        return RouteDecision(False, None, 0.0, "no online worker supports requested model", [])

    eligible.sort(key=lambda item: item["score"], reverse=True)
    best = eligible[0]
    return RouteDecision(
        accepted=True,
        worker_id=best["worker_id"],
        score=round(best["score"], 6),
        reason="worker selected",
        alternatives=[{"worker_id": item["worker_id"], "score": round(item["score"], 6)} for item in eligible[1:]],
    )


def _score_worker(job: dict[str, Any], worker: dict[str, Any]) -> float:
    score = float(worker.get("reputation_score", 50))
    if job.get("region_preference") and job.get("region_preference") == worker.get("region"):
        score += 10
    if float(worker.get("total_vram_gb", 0)) >= _required_vram(job):
        score += 10
    avg_latency = float(worker.get("average_latency_ms", 0) or 0)
    if avg_latency:
        score += max(0, 20 - avg_latency / 500)
    else:
        score += 5
    energy = float(worker.get("average_energy_per_token", 0) or 0)
    if energy:
        score += max(0, 10 - energy / 100)
    else:
        score += 3
    failures = float(worker.get("failure_count", 0))
    successes = float(worker.get("success_count", 0))
    if failures + successes:
        score -= 20 * failures / (failures + successes)
    return score


def _required_vram(job: dict[str, Any]) -> float:
    model = str(job.get("model", ""))
    if "70b" in model.lower():
        return 80
    if "13b" in model.lower():
        return 24
    return 8
