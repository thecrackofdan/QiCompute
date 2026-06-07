from __future__ import annotations

from typing import Any


def run_monetary_simulation(cycles: int = 100) -> dict[str, Any]:
    qi_issued = 0.0
    qi_circulated = 0.0
    qi_spent_on_inference = 0.0
    qi_earned_by_workers = 0.0
    qi_earned_by_verifiers = 0.0
    treasury_fees = 0.0
    worker_hoard = 0.0
    customer_spending_capacity = 3.0
    reinvestment = 0.0
    for cycle in range(max(int(cycles), 0)):
        demand = _demand(cycle)
        mined = 0.018 if demand < 0.4 else 0.006
        qi_issued += mined
        customer_spending_capacity += mined * 0.35
        if demand < 0.25:
            worker_hoard += mined * 0.65
            continue
        spend = min(customer_spending_capacity, 0.04 * demand)
        worker_pay = spend * 0.82
        verifier_pay = spend * 0.08
        fee = spend * 0.10
        qi_spent_on_inference += spend
        qi_earned_by_workers += worker_pay
        qi_earned_by_verifiers += verifier_pay
        treasury_fees += fee
        qi_circulated += spend + worker_pay + verifier_pay + fee
        customer_spending_capacity -= spend
        worker_hoard += worker_pay * 0.55
        reinvestment += worker_pay * 0.25
    qi_hoarded = worker_hoard + max(customer_spending_capacity, 0.0)
    return {
        "cycles": cycles,
        "qi_issued": round(qi_issued, 12),
        "qi_circulated": round(qi_circulated, 12),
        "qi_hoarded": round(qi_hoarded, 12),
        "qi_spent_on_inference": round(qi_spent_on_inference, 12),
        "qi_earned_by_workers": round(qi_earned_by_workers, 12),
        "qi_earned_by_verifiers": round(qi_earned_by_verifiers, 12),
        "treasury_fees": round(treasury_fees, 12),
        "agent_reinvestment": round(reinvestment, 12),
        "idle_mining_fallback": round(qi_issued - min(qi_issued, qi_spent_on_inference), 12),
        "velocity_estimate": round(qi_circulated / max(qi_issued + qi_earned_by_workers + qi_earned_by_verifiers, 1.0), 12),
        "demand_vs_issuance_ratio": round(qi_spent_on_inference / max(qi_issued, 0.000000001), 12),
    }


def _demand(cycle: int) -> float:
    phase = cycle % 30
    if phase < 6:
        return 0.15
    if phase < 16:
        return 0.65
    if phase < 25:
        return 1.1
    return 0.35
