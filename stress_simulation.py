from __future__ import annotations

from typing import Any

import failures
from adversary import FLAKY, HONEST, MALICIOUS_RECEIPT, SLOW, simulate_worker_receipt
from db import WorkerDB
from receipts import verify_receipt_hash, utc_now_iso
from reputation import update_worker_reputation
from router import route_and_audit_inference_job


def run_stress_simulation(db: WorkerDB, config: dict[str, Any], *, seed: int = 7) -> dict[str, Any]:
    workers = _stress_workers()
    for worker in workers:
        db.register_worker(worker)
    jobs = _stress_jobs()
    for job in jobs:
        db.insert_customer_job(job)

    completed = failed = expired = retried = rejected = 0
    route_scores = []
    prices = []
    behaviors = {worker["worker_id"]: worker["metadata"]["behavior"] for worker in workers}
    initial_reputations = {worker["worker_id"]: worker["reputation_score"] for worker in workers}
    for index, job in enumerate(db.list_queued_jobs()):
        if job.get("expires_at") and job["expires_at"] <= utc_now_iso():
            db.expire_stale_customer_jobs(utc_now_iso())
            expired += 1
            continue
        decision = route_and_audit_inference_job(db, job, db.list_online_workers())
        if not decision.accepted or not decision.worker_id:
            db.update_customer_job_status(job["job_id"], "rejected", {"failure_code": decision.failure_code})
            rejected += 1
            continue
        route_scores.append(decision.score)
        db.assign_customer_job(job["job_id"], decision.worker_id, decision.score)
        db.update_customer_job_status(job["job_id"], "running", {})
        db.increment_worker_load(decision.worker_id)
        behavior = behaviors.get(decision.worker_id, HONEST)
        receipt = simulate_worker_receipt(decision.worker_id, job, behavior, attempt=index)
        verification = {"accepted": verify_receipt_hash(receipt) and receipt["metadata"].get("accepted"), "reason": "stress"}
        update_worker_reputation(db, worker_id=decision.worker_id, verification=verification, receipt=receipt)
        db.decrement_worker_load(decision.worker_id)
        if verification["accepted"] and behavior != SLOW:
            db.update_customer_job_status(job["job_id"], "completed", {})
            completed += 1
            prices.append(receipt["estimated_qi_owed"])
        elif job["retry_count"] < 1 and behavior in {FLAKY, SLOW}:
            db.mark_customer_job_failure(job["job_id"], failures.WORKER_TIMEOUT, "simulated timeout", retrying=True)
            retried += 1
        else:
            db.mark_customer_job_failure(job["job_id"], failures.VERIFICATION_FAILED, "simulated failure")
            failed += 1

    all_workers = [db.get_worker(worker["worker_id"]) for worker in workers]
    best = max(all_workers, key=lambda worker: worker["success_count"])
    worst = max(all_workers, key=lambda worker: worker["failure_count"])
    malicious = db.get_worker("stress-worker-malicious")
    return {
        "completed": completed,
        "failed": failed,
        "expired": expired,
        "retried": retried,
        "rejected": rejected,
        "average_route_score": sum(route_scores) / len(route_scores) if route_scores else 0.0,
        "average_final_price": sum(prices) / len(prices) if prices else 0.0,
        "best_worker_by_completed_jobs": best["worker_id"],
        "worst_worker_by_failures": worst["worker_id"],
        "malicious_worker_penalty_observed": malicious["reputation_score"] < initial_reputations["stress-worker-malicious"],
    }


def _stress_workers() -> list[dict[str, Any]]:
    now = utc_now_iso()
    specs = [
        ("stress-worker-good-1", HONEST, ["llama-3.1-8b"], 80),
        ("stress-worker-good-2", HONEST, ["mistral-7b"], 75),
        ("stress-worker-flaky", FLAKY, ["llama-3.1-8b"], 55),
        ("stress-worker-slow", SLOW, ["llama-3.1-8b"], 60),
        ("stress-worker-malicious", MALICIOUS_RECEIPT, ["llama-3.1-8b"], 95),
    ]
    while len(specs) < 10:
        idx = len(specs)
        specs.append((f"stress-worker-{idx}", HONEST, ["llama-3.1-8b" if idx % 2 else "mistral-7b"], 50 + idx))
    return [
        {
            "worker_id": wid,
            "operator": "stress",
            "region": "us-east" if i % 2 else "us-west",
            "public_key": "placeholder",
            "endpoint": "local",
            "hardware_profile": {"gpu_count": 1, "gpu_names": [wid], "total_vram_gb": 24},
            "supported_modes": ["inference", "mining"],
            "supported_models": models,
            "gpu_count": 1,
            "total_vram_gb": 24,
            "total_watts_capacity": 300,
            "online": i != 9,
            "last_seen_at": now,
            "reputation_score": rep,
            "success_count": 0,
            "failure_count": 0,
            "average_latency_ms": 1000 + i * 100,
            "average_energy_per_token": 8,
            "current_jobs": 0,
            "max_concurrent_jobs": 2,
            "metadata": {"behavior": behavior},
        }
        for i, (wid, behavior, models, rep) in enumerate(specs)
    ]


def _stress_jobs() -> list[dict[str, Any]]:
    now = utc_now_iso()
    jobs = []
    for i in range(50):
        jobs.append(
            {
                "job_id": f"stress-job-{i}",
                "customer_id": "stress-customer",
                "model": "llama-3.1-8b" if i % 3 else "mistral-7b",
                "prompt_hash": f"stress-hash-{i}",
                "input_tokens": 50 + i,
                "expected_output_tokens": 100 + i,
                "privacy_level": "standard" if i % 2 else "private",
                "max_price_qi": 0.001,
                "status": "queued",
                "created_at": now,
                "expires_at": "2000-01-01T00:00:00+00:00" if i in {5, 15} else "9999-01-01T00:00:00+00:00",
                "metadata": {"latency_target_ms": 1000 + i * 10},
            }
        )
    return jobs
