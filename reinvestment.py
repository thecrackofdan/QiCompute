from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReinvestmentResult:
    action: str
    reserve_qi: float
    spent_qi: float
    worker_count: int
    verification_capacity: float
    simulated_capacity_growth: float
    profit_growth: float
    utilization_growth: float

    def to_dict(self) -> dict[str, float | int | str]:
        return {
            "action": self.action,
            "reserve_qi": self.reserve_qi,
            "spent_qi": self.spent_qi,
            "worker_count": self.worker_count,
            "verification_capacity": self.verification_capacity,
            "simulated_capacity_growth": self.simulated_capacity_growth,
            "profit_growth": self.profit_growth,
            "utilization_growth": self.utilization_growth,
        }


def simulate_reinvestment(
    *,
    qi_balance: float,
    worker_count: int,
    verification_capacity: float,
    expected_profit: float,
    policy: dict[str, float],
) -> ReinvestmentResult:
    reserve = max(float(policy.get("reserve_qi", 0.0)), 0.0)
    expandable = max(float(qi_balance) - reserve, 0.0)
    worker_cost = max(float(policy.get("worker_expansion_cost_qi", 1.0)), 0.000000001)
    verifier_cost = max(float(policy.get("verification_capacity_cost_qi", 0.5)), 0.000000001)
    if expandable >= worker_cost and expected_profit > 0:
        added_workers = int(expandable // worker_cost)
        spent = added_workers * worker_cost
        new_workers = worker_count + added_workers
        capacity_growth = added_workers / max(worker_count, 1)
        return ReinvestmentResult(
            action="expand_worker_count",
            reserve_qi=round(float(qi_balance) - spent, 12),
            spent_qi=round(spent, 12),
            worker_count=new_workers,
            verification_capacity=round(float(verification_capacity), 12),
            simulated_capacity_growth=round(capacity_growth, 12),
            profit_growth=round(capacity_growth * max(float(expected_profit), 0.0), 12),
            utilization_growth=round(min(capacity_growth, 1.0), 12),
        )
    if expandable >= verifier_cost and expected_profit > 0:
        added_capacity = expandable / verifier_cost
        spent = expandable
        return ReinvestmentResult(
            action="increase_verification_capacity",
            reserve_qi=round(float(qi_balance) - spent, 12),
            spent_qi=round(spent, 12),
            worker_count=worker_count,
            verification_capacity=round(float(verification_capacity) + added_capacity, 12),
            simulated_capacity_growth=0.0,
            profit_growth=round(added_capacity * 0.01 * max(float(expected_profit), 0.0), 12),
            utilization_growth=round(min(added_capacity * 0.01, 1.0), 12),
        )
    return ReinvestmentResult(
        action="keep_reserve",
        reserve_qi=round(float(qi_balance), 12),
        spent_qi=0.0,
        worker_count=worker_count,
        verification_capacity=round(float(verification_capacity), 12),
        simulated_capacity_growth=0.0,
        profit_growth=0.0,
        utilization_growth=0.0,
    )
