from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import failures
from db import WorkerDB
from receipts import utc_now_iso


@dataclass(frozen=True)
class RouteDecision:
    accepted: bool
    worker_id: str | None
    score: float
    reason: str
    failure_code: str | None = None
    alternatives: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "worker_id": self.worker_id,
            "score": self.score,
            "reason": self.reason,
            "failure_code": self.failure_code,
            "alternatives": self.alternatives,
        }


def route_inference_job(job: dict[str, Any], workers: list[dict[str, Any]]) -> RouteDecision:
    if job.get("expires_at") and str(job["expires_at"]) <= utc_now_iso():
        return RouteDecision(False, None, 0.0, "job expired", failures.JOB_EXPIRED, [])
    eligible = []
    skipped_overloaded = False
    for worker in workers:
        if not worker.get("online"):
            continue
        if job["model"] not in worker.get("supported_models", []):
            continue
        if int(worker.get("current_jobs", 0)) >= int(worker.get("max_concurrent_jobs", 1)):
            skipped_overloaded = True
            continue
        if job.get("requires_gpu", True) and float(worker.get("gpu_count", 0)) <= 0:
            continue
        score = _score_worker(job, worker)
        eligible.append({"worker_id": worker["worker_id"], "score": score, "worker": worker})

    if not eligible:
        code = failures.WORKER_OVERLOADED if skipped_overloaded else failures.MODEL_NOT_SUPPORTED
        return RouteDecision(
            False,
            None,
            0.0,
            "no online worker supports requested model",
            code,
            [],
        )

    eligible.sort(key=lambda item: item["score"], reverse=True)
    best = eligible[0]
    return RouteDecision(
        accepted=True,
        worker_id=best["worker_id"],
        score=round(best["score"], 6),
        reason="worker selected",
        failure_code=None,
        alternatives=[{"worker_id": item["worker_id"], "score": round(item["score"], 6)} for item in eligible[1:]],
    )


def route_and_audit_inference_job(
    db: WorkerDB,
    job: dict[str, Any],
    workers: list[dict[str, Any]],
    *,
    envelope_id: str | None = None,
    router_version: str = "local-v1",
) -> RouteDecision:
    decision = route_inference_job(job, workers)
    db.insert_routing_audit_log(
        {
            "audit_id": str(uuid4()),
            "job_id": job["job_id"],
            "envelope_id": envelope_id,
            "selected_worker_id": decision.worker_id,
            "selected_score": decision.score,
            "accepted": decision.accepted,
            "reason": decision.failure_code or decision.reason,
            "alternatives": decision.alternatives,
            "router_version": router_version,
            "created_at": utc_now_iso(),
            "metadata": {"reason": decision.reason, "failure_code": decision.failure_code},
        }
    )
    return decision


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
    load_percent = float(worker.get("load_percent", 0) or 0)
    score += max(0, 20 - load_percent / 5)
    metadata = worker.get("metadata", {})
    loaded_models = metadata.get("loaded_models", [])
    if job.get("model") in loaded_models:
        score += 15
    else:
        score -= float(metadata.get("model_load_latency_ms", 0) or 0) / 1000
        score -= float(metadata.get("cold_load_count", 0) or 0)
    if float(metadata.get("estimated_vram_available_gb", worker.get("total_vram_gb", 0)) or 0) < _required_vram(job):
        score -= 25
    score -= 5 * float(metadata.get("recent_runtime_failures", 0) or 0)
    score += min(10, float(metadata.get("tokens_per_second", 0) or 0) / 50)
    return score


def _required_vram(job: dict[str, Any]) -> float:
    model = str(job.get("model", ""))
    if "70b" in model.lower():
        return 80
    if "13b" in model.lower():
        return 24
    return 8
