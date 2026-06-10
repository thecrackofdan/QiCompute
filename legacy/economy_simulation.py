from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any

from economic_scheduler import choose_economic_action
from economy_report import build_economy_report
from market_demand import estimate_inference_opportunity, estimate_market_demand
from mining_economics import estimate_mining_opportunity


@dataclass
class SimAgent:
    agent_id: str
    gpu_count: int
    worker_count: int
    role: str
    qi_balance: float = 0.0
    mined_qi: float = 0.0
    earned_qi: float = 0.0
    spent_qi: float = 0.0
    total_profit: float = 0.0
    utilization: float = 0.0


def run_economy_simulation(cycles: int = 100, seed: int = 7) -> dict[str, Any]:
    agents = [
        SimAgent("agent-a-3090", gpu_count=1, worker_count=1, role="hybrid"),
        SimAgent("agent-b-2x3080", gpu_count=2, worker_count=2, role="hybrid"),
        SimAgent("agent-c-verifier", gpu_count=1, worker_count=0, role="verifier"),
        SimAgent("agent-d-inference", gpu_count=1, worker_count=1, role="inference_worker"),
    ]
    totals = {
        "agent_count": len(agents),
        "total_cycles": cycles * len(agents),
        "mined_qi": 0.0,
        "earned_qi": 0.0,
        "spent_qi": 0.0,
        "inference_volume": 0.0,
        "mining_volume": 0.0,
        "verification_volume": 0.0,
        "idle_cycles": 0.0,
        "market_demand_served": 0.0,
        "total_profit": 0.0,
    }
    for cycle in range(max(int(cycles), 0)):
        queued_jobs = _deterministic_demand(cycle, seed)
        demand = estimate_market_demand(
            queued_jobs=queued_jobs,
            waiting_customers=max(queued_jobs - 2, 0),
            expected_inference_revenue=queued_jobs * 0.00008,
            average_queue_latency=queued_jobs * 12,
            active_workers=sum(max(agent.worker_count, 1) for agent in agents),
        )
        for agent in agents:
            mining = estimate_mining_opportunity(
                gpu_count=agent.gpu_count,
                hash_rate_per_gpu=0.8 if agent.gpu_count == 1 else 0.7,
                network_difficulty=10000,
                power_watts=280,
                energy_cost_per_kwh=0.00001,
                expected_block_reward_qi=0.5,
            )
            inference = estimate_inference_opportunity(
                demand,
                worker_count=agent.worker_count,
                energy_cost_per_hour=0.000003,
                max_jobs_per_worker_hour=1,
            )
            verification = {
                "expected_qi_per_hour": 0.00002 * min(demand.queued_jobs, 4) if agent.role in {"verifier", "hybrid"} else 0.0,
                "expected_cost_per_hour": 0.000001,
            }
            routing = {
                "expected_qi_per_hour": 0.00001 * min(demand.waiting_customers, 4),
                "expected_cost_per_hour": 0.0000005,
            }
            decision = choose_economic_action(
                current_qi_balance=agent.qi_balance,
                mining_profitability=mining.to_dict(),
                inference_demand=inference.to_dict(),
                verification_demand=verification,
                routing_demand=routing,
                worker_utilization=demand.utilization_pressure,
                energy_cost=0.000002,
                policy_settings={"minimum_profit_qi": 0.0, "reserve_qi": 0.0001},
            )
            _apply_decision(agent, decision.to_dict(), totals)
    report = build_economy_report(totals)
    report.update(
        {
            "cycles": cycles,
            "treasury_growth": round(sum(agent.qi_balance for agent in agents), 12),
            "market_demand_served": round(totals["market_demand_served"], 12),
            "utilization": round(sum(agent.utilization for agent in agents) / max(len(agents) * max(cycles, 1), 1), 12),
        }
    )
    return report


def _apply_decision(agent: SimAgent, decision: dict[str, Any], totals: dict[str, float]) -> None:
    action = decision["chosen_action"]
    expected_qi = float(decision["expected_qi"])
    expected_cost = float(decision["expected_cost"])
    expected_profit = float(decision["expected_profit"])
    if action == "mine":
        agent.mined_qi += expected_qi
        totals["mined_qi"] += expected_qi
        totals["mining_volume"] += expected_qi
        agent.utilization += 1
    elif action == "serve_inference":
        agent.earned_qi += expected_qi
        totals["earned_qi"] += expected_qi
        totals["inference_volume"] += expected_qi
        totals["market_demand_served"] += 1
        agent.utilization += 1
    elif action == "verify":
        agent.earned_qi += expected_qi
        totals["earned_qi"] += expected_qi
        totals["verification_volume"] += expected_qi
        agent.utilization += 1
    elif action == "route":
        agent.earned_qi += expected_qi
        totals["earned_qi"] += expected_qi
        agent.utilization += 0.5
    else:
        totals["idle_cycles"] += 1
    agent.qi_balance += expected_qi - expected_cost
    agent.total_profit += expected_profit
    totals["total_profit"] += expected_profit


def _deterministic_demand(cycle: int, seed: int) -> int:
    phase = (cycle + seed) % 20
    if phase < 4:
        return 0
    if phase < 10:
        return 2
    if phase < 16:
        return 6
    return 12


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic QiCompute autonomous economy simulation")
    parser.add_argument("--cycles", type=int, default=100)
    args = parser.parse_args()
    report = run_economy_simulation(args.cycles)
    print(
        "economy_simulation "
        f"cycles={report['cycles']} "
        f"total_qi_mined={report['total_qi_mined']:.12f} "
        f"total_qi_transferred={report['total_qi_transferred']:.12f} "
        f"total_inference_volume={report['total_inference_volume']:.12f} "
        f"utilization={report['utilization']:.12f} "
        f"treasury_growth={report['treasury_growth']:.12f} "
        f"market_demand_served={report['market_demand_served']:.12f}"
    )


if __name__ == "__main__":
    main()
