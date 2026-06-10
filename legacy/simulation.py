from __future__ import annotations

from typing import Any

from db import WorkerDB
import failures
from receipts import make_receipt, utc_now_iso
from reputation import update_worker_reputation
from router import route_and_audit_inference_job


def run_marketplace_simulation(db: WorkerDB, config: dict[str, Any]) -> dict[str, Any]:
    workers = _fake_workers()
    for worker in workers:
        db.register_worker(worker)

    jobs = _fake_jobs()
    for job in jobs:
        db.insert_customer_job(job)

    routed = 0
    rejected = 0
    completed = 0
    retried = 0
    expired = 0
    failed = 0
    latencies = []
    route_scores = []
    for job in db.list_queued_jobs():
        decision = route_and_audit_inference_job(db, job, db.list_online_workers())
        if decision.accepted and decision.worker_id:
            db.assign_customer_job(job["job_id"], decision.worker_id, decision.score)
            db.update_customer_job_status(job["job_id"], "running", {})
            db.increment_worker_load(decision.worker_id)
            routed += 1
            route_scores.append(decision.score)
            receipt = _simulated_receipt(decision.worker_id, job, accepted=True)
            latencies.append(receipt["duration_seconds"] * 1000)
            update_worker_reputation(
                db,
                worker_id=decision.worker_id,
                verification={"accepted": True, "reason": "simulation accepted"},
                receipt=receipt,
            )
            db.decrement_worker_load(decision.worker_id)
            db.update_customer_job_status(job["job_id"], "completed", {})
            completed += 1
        else:
            db.update_customer_job_status(job["job_id"], "rejected", {"failure_code": decision.failure_code})
            rejected += 1

    return {
        "workers_registered": len(workers),
        "jobs_submitted": len(jobs),
        "jobs_routed": routed,
        "jobs_rejected": rejected,
        "jobs_completed": completed,
        "jobs_retried": retried,
        "jobs_expired": expired,
        "jobs_failed": failed,
        "online_workers": len(db.list_online_workers()),
        "offline_workers": 0,
        "average_latency": sum(latencies) / len(latencies) if latencies else 0.0,
        "average_route_score": sum(route_scores) / len(route_scores) if route_scores else 0.0,
        "route_success_rate": routed / len(jobs) if jobs else 0.0,
        "audit_logs": len(db.recent_routing_audit_logs(100)),
        "reputation": [
            {
                "worker_id": worker["worker_id"],
                "reputation_score": worker["reputation_score"],
                "success_count": worker["success_count"],
                "failure_count": worker["failure_count"],
            }
            for worker in db.list_online_workers()
        ],
    }


def _fake_workers() -> list[dict[str, Any]]:
    now = utc_now_iso()
    return [
        {
            "worker_id": "sim-worker-a",
            "operator": "sim",
            "region": "us-east",
            "public_key": "placeholder",
            "endpoint": "local",
            "hardware_profile": {"gpu_count": 1, "gpu_names": ["sim-a"], "total_vram_gb": 24},
            "supported_modes": ["inference", "mining"],
            "supported_models": ["llama-3.1-8b"],
            "gpu_count": 1,
            "total_vram_gb": 24,
            "total_watts_capacity": 320,
            "online": True,
            "last_seen_at": now,
            "reputation_score": 70,
            "success_count": 5,
            "failure_count": 1,
            "average_latency_ms": 1200,
            "average_energy_per_token": 8,
            "current_jobs": 0,
            "max_concurrent_jobs": 2,
            "load_percent": 0,
            "last_heartbeat_at": now,
            "metadata": {},
        },
        {
            "worker_id": "sim-worker-b",
            "operator": "sim",
            "region": "us-west",
            "public_key": "placeholder",
            "endpoint": "local",
            "hardware_profile": {"gpu_count": 1, "gpu_names": ["sim-b"], "total_vram_gb": 16},
            "supported_modes": ["inference", "mining"],
            "supported_models": ["mistral-7b"],
            "gpu_count": 1,
            "total_vram_gb": 16,
            "total_watts_capacity": 260,
            "online": True,
            "last_seen_at": now,
            "reputation_score": 55,
            "success_count": 2,
            "failure_count": 1,
            "average_latency_ms": 1800,
            "average_energy_per_token": 10,
            "current_jobs": 0,
            "max_concurrent_jobs": 2,
            "load_percent": 0,
            "last_heartbeat_at": now,
            "metadata": {},
        },
    ]


def _fake_jobs() -> list[dict[str, Any]]:
    now = utc_now_iso()
    return [
        {
            "job_id": "sim-job-1",
            "customer_id": "sim-customer",
            "model": "llama-3.1-8b",
            "prompt_hash": "sim-hash-1",
            "input_tokens": 100,
            "expected_output_tokens": 300,
            "privacy_level": "standard",
            "max_price_qi": 0.001,
            "status": "queued",
            "created_at": now,
            "expires_at": "9999-01-01T00:00:00+00:00",
            "metadata": {},
        },
        {
            "job_id": "sim-job-2",
            "customer_id": "sim-customer",
            "model": "unsupported-model",
            "prompt_hash": "sim-hash-2",
            "input_tokens": 50,
            "expected_output_tokens": 100,
            "privacy_level": "standard",
            "max_price_qi": 0.001,
            "status": "queued",
            "created_at": now,
            "expires_at": "9999-01-01T00:00:00+00:00",
            "metadata": {},
        },
    ]


def _simulated_receipt(worker_id: str, job: dict[str, Any], *, accepted: bool) -> dict[str, Any]:
    return make_receipt(
        worker_id=worker_id,
        mode="inference",
        started_at=utc_now_iso(),
        ended_at=utc_now_iso(),
        duration_seconds=1,
        average_watts=250,
        output_type="tokens",
        output_amount=job["expected_output_tokens"],
        estimated_qi_owed=0.0001,
        metadata={
            "job_id": job["job_id"],
            "accepted": accepted,
            "input_tokens": job["input_tokens"],
            "output_tokens": job["expected_output_tokens"],
        },
    ).to_dict()
