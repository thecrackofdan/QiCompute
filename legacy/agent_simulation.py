from __future__ import annotations

from typing import Any

from agents import (
    agent_balance,
    choose_agent_action,
    create_agent_account,
    credit_agent_for_verified_worker_job,
    fund_agent_job_escrow,
    get_agent_account,
    record_agent_mining_income,
    spend_agent_job_escrow,
)
from db import WorkerDB


def run_agent_simulation(db: WorkerDB | None = None) -> dict[str, Any]:
    """Run a deterministic simulation of agent balances and policy choices."""
    owns_db = db is None
    db = db or WorkerDB(":memory:")
    try:
        agent = create_agent_account(
            db,
            agent_id="sim-agent",
            operator_id="human-operator",
            worker_id="human-rig-worker",
            customer_id="sim-customer",
            role="hybrid",
            metadata={"rig": "human-owned-gpu-rig"},
        )
        config = {"minimum_profit_qi_per_hour": 0.00001}
        periods = [
            {
                "name": "low-demand",
                "hours": 3,
                "market_state": {
                    "inference_demand": 0.05,
                    "inference_qi_per_hour": 0.0002,
                    "mining_qi_per_hour": 0.00008,
                    "verification_qi_per_hour": 0.00002,
                    "verification_demand": 0,
                },
            },
            {
                "name": "high-demand",
                "hours": 4,
                "market_state": {
                    "inference_demand": 1.0,
                    "inference_qi_per_hour": 0.0003,
                    "mining_qi_per_hour": 0.00008,
                    "verification_qi_per_hour": 0.00002,
                    "verification_demand": 0.2,
                },
            },
        ]
        jobs_served = 0
        mining_fallback_time = 0
        active_hours = 0
        for period in periods:
            for hour in range(period["hours"]):
                agent = get_agent_account(db, "sim-agent")
                action = choose_agent_action(agent, period["market_state"], config)
                if action == "mine":
                    record_agent_mining_income(db, "sim-agent", period["market_state"]["mining_qi_per_hour"])
                    mining_fallback_time += 1
                    active_hours += 1
                elif action == "serve_inference":
                    receipt_id = f"{period['name']}-receipt-{hour}"
                    credit_agent_for_verified_worker_job(
                        db,
                        worker_id="human-rig-worker",
                        receipt_id=receipt_id,
                        job_id=f"{period['name']}-job-{hour}",
                        qi_amount=period["market_state"]["inference_qi_per_hour"],
                        verification={"accepted": True, "reason": "simulation accepted"},
                        metadata={"period": period["name"]},
                    )
                    jobs_served += 1
                    active_hours += 1

        submit_cost = min(0.0001, agent_balance(db, "sim-agent"))
        if submit_cost > 0:
            fund_agent_job_escrow(db, agent_id="sim-agent", job_id="agent-submit-job", qi_amount=submit_cost)
            spend_agent_job_escrow(db, "agent-submit-job")

        final = get_agent_account(db, "sim-agent")
        total_hours = sum(period["hours"] for period in periods)
        return {
            "mined_qi": round(final["mined_qi"], 12),
            "earned_qi": round(final["earned_qi"], 12),
            "spent_qi": round(final["spent_qi"], 12),
            "final_balance": round(final["qi_balance"], 12),
            "inference_jobs_served": jobs_served,
            "mining_fallback_time": mining_fallback_time,
            "utilization_ratio": round(active_hours / total_hours if total_hours else 0, 6),
        }
    finally:
        if owns_db:
            db.close()


def main() -> None:
    metrics = run_agent_simulation()
    print(
        "agent_simulation "
        f"mined_qi={metrics['mined_qi']:.12f} "
        f"earned_qi={metrics['earned_qi']:.12f} "
        f"spent_qi={metrics['spent_qi']:.12f} "
        f"final_balance={metrics['final_balance']:.12f} "
        f"inference_jobs_served={metrics['inference_jobs_served']} "
        f"mining_fallback_time={metrics['mining_fallback_time']} "
        f"utilization_ratio={metrics['utilization_ratio']:.6f}"
    )


if __name__ == "__main__":
    main()
