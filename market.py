from __future__ import annotations

import argparse
import hashlib
from uuid import uuid4

from db import WorkerDB
from logging_config import configure_logging, log_event
from pricing import estimate_job_price
from receipts import utc_now_iso
from registry import heartbeat_local_worker, register_local_worker
from router import route_and_audit_inference_job
from simulation import run_marketplace_simulation
from stress_simulation import run_stress_simulation
from worker import load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Local QiCompute marketplace prototype")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--register-worker", action="store_true")
    parser.add_argument("--workers", action="store_true")
    parser.add_argument("--submit-job", action="store_true")
    parser.add_argument("--model", default="llama-3.1-8b")
    parser.add_argument("--input-tokens", type=float, default=100)
    parser.add_argument("--output-tokens", type=float, default=500)
    parser.add_argument("--privacy-level", default="standard")
    parser.add_argument("--max-price-qi", type=float, default=0.001)
    parser.add_argument("--route-jobs", action="store_true")
    parser.add_argument("--queued-jobs", action="store_true")
    parser.add_argument("--reputation", action="store_true")
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--stress-sim", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    logger = configure_logging(verbose=args.verbose, quiet=args.quiet)
    log_event(logger, "market.command", config=args.config)

    config = load_config(args.config)
    db = WorkerDB(config["worker"]["db_path"])
    try:
        if args.register_worker:
            worker = register_local_worker(db, config)
            heartbeat_local_worker(db, worker["worker_id"], {"source": "market-cli"})
            print(f"registered worker={worker['worker_id']} models={','.join(worker['supported_models'])}")
            return
        if args.workers:
            for worker in db.list_online_workers():
                print(
                    f"{worker['worker_id']} online={worker['online']} "
                    f"region={worker['region']} reputation={worker['reputation_score']:.2f} "
                    f"models={','.join(worker['supported_models'])}"
                )
            return
        if args.submit_job:
            job_id = str(uuid4())
            price = estimate_job_price(
                input_tokens=args.input_tokens,
                output_tokens=args.output_tokens,
                model=args.model,
                privacy_level=args.privacy_level,
                latency_target=None,
                energy_joules=0,
                worker_reputation=50,
                config=config,
            )
            db.insert_customer_job(
                {
                    "job_id": job_id,
                    "customer_id": "local-customer",
                    "model": args.model,
                    "prompt_hash": _placeholder_prompt_hash(job_id),
                    "input_tokens": args.input_tokens,
                    "expected_output_tokens": args.output_tokens,
                    "privacy_level": args.privacy_level,
                    "max_price_qi": args.max_price_qi,
                    "status": "queued",
                    "created_at": utc_now_iso(),
                    "metadata": {"price": price.to_dict()},
                }
            )
            print(f"queued job={job_id} model={args.model} estimated_price_qi={price.estimated_price_qi:.12f}")
            return
        if args.route_jobs:
            _route_jobs(db)
            return
        if args.queued_jobs:
            for job in db.list_queued_jobs():
                print(f"{job['job_id']} model={job['model']} status={job['status']} max_price_qi={job['max_price_qi']}")
            return
        if args.reputation:
            for worker in db.list_online_workers():
                print(
                    f"{worker['worker_id']} reputation={worker['reputation_score']:.2f} "
                    f"success={worker['success_count']} failure={worker['failure_count']}"
                )
            return
        if args.simulate:
            summary = run_marketplace_simulation(db, config)
            print(
                f"simulation workers={summary['workers_registered']} "
                f"jobs={summary['jobs_submitted']} routed={summary['jobs_routed']} "
                f"rejected={summary['jobs_rejected']} "
                f"avg_score={summary['average_route_score']:.4f} "
                f"audit_logs={summary['audit_logs']}"
            )
            for worker in summary["reputation"]:
                print(
                    f"worker={worker['worker_id']} reputation={worker['reputation_score']:.2f} "
                    f"success={worker['success_count']} failure={worker['failure_count']}"
                )
            return
        if args.stress_sim:
            summary = run_stress_simulation(db, config)
            print(
                f"stress completed={summary['completed']} failed={summary['failed']} "
                f"expired={summary['expired']} retried={summary['retried']} "
                f"rejected={summary['rejected']} avg_score={summary['average_route_score']:.4f} "
                f"avg_price={summary['average_final_price']:.12f} "
                f"best={summary['best_worker_by_completed_jobs']} worst={summary['worst_worker_by_failures']} "
                f"malicious_penalty={summary['malicious_worker_penalty_observed']}"
            )
            return
        parser.print_help()
    finally:
        db.close()


def _route_jobs(db: WorkerDB) -> None:
    db.expire_stale_customer_jobs(utc_now_iso())
    workers = db.list_online_workers()
    for job in db.list_queued_jobs():
        route_job = {
            "job_id": job["job_id"],
            "model": job["model"],
            "input_tokens": job["input_tokens"],
            "expected_output_tokens": job["expected_output_tokens"],
            "max_price_qi": job["max_price_qi"],
            "privacy_level": job["privacy_level"],
            "requires_gpu": True,
            "expires_at": job.get("expires_at"),
        }
        decision = route_and_audit_inference_job(
            db,
            route_job,
            workers,
        )
        if decision.accepted and decision.worker_id:
            db.assign_customer_job(job["job_id"], decision.worker_id, decision.score)
            print(f"routed job={job['job_id']} worker={decision.worker_id} score={decision.score:.4f}")
        else:
            if job["status"] == "retrying":
                db.mark_customer_job_failure(job["job_id"], decision.failure_code or "ROUTE_FAILED", decision.reason)
            else:
                db.update_customer_job_status(
                    job["job_id"],
                    "rejected",
                    {"route_reason": decision.reason, "failure_code": decision.failure_code},
                )
            print(f"rejected job={job['job_id']} reason={decision.failure_code or decision.reason}")


def _placeholder_prompt_hash(job_id: str) -> str:
    return hashlib.sha256(f"placeholder:{job_id}".encode("utf-8")).hexdigest()


if __name__ == "__main__":
    main()
