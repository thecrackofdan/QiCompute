from __future__ import annotations

from dataclasses import dataclass
from typing import Any


STRATEGIES = (
    "mining_specialist",
    "inference_specialist",
    "verifier_specialist",
    "balanced_operator",
    "aggressive_reinvestor",
    "conservative_reserve_holder",
)


@dataclass
class CompetitiveAgent:
    strategy: str
    qi_balance: float = 1.0
    mined_qi: float = 0.0
    earned_qi: float = 0.0
    spent_qi: float = 0.0
    worker_count: int = 1
    served_jobs: float = 0.0
    active_cycles: int = 0


def run_agent_competition(cycles: int = 100) -> dict[str, Any]:
    agents = [CompetitiveAgent(strategy) for strategy in STRATEGIES]
    total_served = 0.0
    for cycle in range(max(int(cycles), 0)):
        demand_pressure = _demand_pressure(cycle)
        for agent in agents:
            mined, earned, spent, served = _strategy_step(agent, demand_pressure, cycle)
            agent.mined_qi += mined
            agent.earned_qi += earned
            agent.spent_qi += spent
            agent.qi_balance += mined + earned - spent
            agent.served_jobs += served
            agent.active_cycles += 1 if mined or earned or served else 0
            total_served += served
            if agent.strategy == "aggressive_reinvestor" and agent.qi_balance > 1.8:
                agent.qi_balance -= 0.5
                agent.spent_qi += 0.5
                agent.worker_count += 1
            if agent.strategy == "conservative_reserve_holder" and agent.qi_balance < 0.8:
                agent.mined_qi += 0.03
                agent.qi_balance += 0.03
    by_strategy = {}
    survivors = 0
    for agent in agents:
        if agent.qi_balance > 0:
            survivors += 1
        by_strategy[agent.strategy] = {
            "final_qi_balance": round(agent.qi_balance, 12),
            "mined_qi": round(agent.mined_qi, 12),
            "earned_qi": round(agent.earned_qi, 12),
            "spent_qi": round(agent.spent_qi, 12),
            "worker_growth": agent.worker_count - 1,
            "market_share": round(agent.served_jobs / max(total_served, 1.0), 12),
            "utilization": round(agent.active_cycles / max(cycles, 1), 12),
        }
    return {
        "cycles": cycles,
        "strategies": by_strategy,
        "survival_rate": round(survivors / len(agents), 12),
        "market_share": {strategy: values["market_share"] for strategy, values in by_strategy.items()},
        "utilization": round(sum(values["utilization"] for values in by_strategy.values()) / len(by_strategy), 12),
    }


def _strategy_step(agent: CompetitiveAgent, demand_pressure: float, cycle: int) -> tuple[float, float, float, float]:
    mining = 0.015
    inference = 0.045 * demand_pressure * agent.worker_count
    verification = 0.012 * min(1.0, demand_pressure + 0.2)
    if agent.strategy == "mining_specialist":
        return (mining * 1.35, 0.0, 0.0, 0.0)
    if agent.strategy == "inference_specialist":
        served = min(agent.worker_count, 1 + int(demand_pressure * 3))
        return (0.0 if demand_pressure > 0.35 else mining * 0.4, inference, 0.004, served)
    if agent.strategy == "verifier_specialist":
        return (0.0, verification * 1.5, 0.001, 0.0)
    if agent.strategy == "aggressive_reinvestor":
        served = min(agent.worker_count, 1 + int(demand_pressure * 4))
        return (0.0 if demand_pressure > 0.2 else mining * 0.5, inference * 1.1, 0.01, served)
    if agent.strategy == "conservative_reserve_holder":
        return (mining if demand_pressure < 0.75 else mining * 0.4, inference * 0.45, 0.001, demand_pressure)
    served = min(agent.worker_count, 1 + int(demand_pressure * 2))
    return (mining if demand_pressure < 0.45 else 0.0, inference * 0.9 + verification * 0.3, 0.003, served)


def _demand_pressure(cycle: int) -> float:
    phase = cycle % 24
    if phase < 5:
        return 0.15
    if phase < 12:
        return 0.55
    if phase < 20:
        return 0.95
    return 1.25
