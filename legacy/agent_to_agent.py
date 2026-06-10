from __future__ import annotations

from typing import Any


AGENT_ROLES = ("research_agent", "compute_agent", "verifier_agent", "router_agent", "operator_agent")


def simulate_agent_to_agent_economy(cycles: int = 100) -> dict[str, Any]:
    balances = {
        "research_agent": 5.0,
        "compute_agent": 1.0,
        "verifier_agent": 1.0,
        "router_agent": 1.0,
        "operator_agent": 1.0,
    }
    volume = 0.0
    failed_trades = 0
    disputes = 0
    circulated = 0.0
    for cycle in range(max(int(cycles), 0)):
        job_price = 0.035 + (cycle % 5) * 0.002
        verifier_fee = 0.004
        router_fee = 0.002
        operator_fee = 0.003
        total_price = job_price + verifier_fee + router_fee + operator_fee
        if balances["research_agent"] < total_price:
            failed_trades += 1
            continue
        balances["research_agent"] -= total_price
        if cycle % 17 == 0 and cycle != 0:
            disputes += 1
            balances["research_agent"] += total_price * 0.7
            balances["compute_agent"] += job_price * 0.15
            circulated += total_price * 0.3
            continue
        balances["compute_agent"] += job_price
        balances["verifier_agent"] += verifier_fee
        balances["router_agent"] += router_fee
        balances["operator_agent"] += operator_fee
        volume += 1
        circulated += total_price
    return {
        "cycles": cycles,
        "qi_velocity_between_agents": round(circulated / max(sum(balances.values()), 1.0), 12),
        "service_volume": volume,
        "agent_profitability": {role: round(balance - (5.0 if role == "research_agent" else 1.0), 12) for role, balance in balances.items()},
        "failed_trades": failed_trades,
        "dispute_rate": round(disputes / max(cycles, 1), 12),
        "final_balances": {role: round(balance, 12) for role, balance in balances.items()},
    }
