from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ECONOMIC_ACTIONS = ("mine", "serve_inference", "verify", "route", "idle")


@dataclass(frozen=True)
class EconomicDecision:
    chosen_action: str
    expected_qi: float
    expected_cost: float
    expected_profit: float
    reasoning: str

    def to_dict(self) -> dict[str, float | str]:
        return {
            "chosen_action": self.chosen_action,
            "expected_qi": self.expected_qi,
            "expected_cost": self.expected_cost,
            "expected_profit": self.expected_profit,
            "reasoning": self.reasoning,
        }


def choose_economic_action(
    *,
    current_qi_balance: float,
    mining_profitability: dict[str, Any],
    inference_demand: dict[str, Any],
    verification_demand: dict[str, Any],
    routing_demand: dict[str, Any],
    worker_utilization: float,
    energy_cost: float,
    policy_settings: dict[str, Any],
) -> EconomicDecision:
    min_profit = float(policy_settings.get("minimum_profit_qi", 0.0))
    reserve = float(policy_settings.get("reserve_qi", 0.0))
    allowed = set(policy_settings.get("allowed_actions", ECONOMIC_ACTIONS))
    utilization = min(max(float(worker_utilization), 0.0), 1.0)
    energy = max(float(energy_cost), 0.0)
    opportunities = {
        "mine": _opportunity(
            mining_profitability,
            qi_key="expected_qi_per_hour",
            cost_key="expected_cost_per_hour",
            profit_key="expected_profit_per_hour",
        ),
        "serve_inference": _opportunity(
            inference_demand,
            qi_key="expected_qi_per_hour",
            cost_key="expected_cost_per_hour",
            profit_key="expected_profit_per_hour",
            default_qi_key="expected_inference_revenue",
        ),
        "verify": _opportunity(
            verification_demand,
            qi_key="expected_qi_per_hour",
            cost_key="expected_cost_per_hour",
            profit_key="expected_profit_per_hour",
        ),
        "route": _opportunity(
            routing_demand,
            qi_key="expected_qi_per_hour",
            cost_key="expected_cost_per_hour",
            profit_key="expected_profit_per_hour",
        ),
        "idle": (0.0, 0.0, 0.0),
    }
    if current_qi_balance < reserve and "mine" in opportunities:
        qi, cost, profit = opportunities["mine"]
        opportunities["mine"] = (qi, cost, profit + float(policy_settings.get("reserve_mining_bias", 0.0)))
    if utilization >= float(policy_settings.get("high_utilization_threshold", 0.9)):
        qi, cost, profit = opportunities["mine"]
        opportunities["mine"] = (qi, cost + energy, profit - energy)
    ranked = sorted(
        (
            (action, values)
            for action, values in opportunities.items()
            if action in allowed and values[2] >= min_profit
        ),
        key=lambda item: (item[1][2], _action_rank(item[0])),
        reverse=True,
    )
    if not ranked:
        return EconomicDecision("idle", 0.0, 0.0, 0.0, "no action met minimum profit")
    action, (expected_qi, expected_cost, expected_profit) = ranked[0]
    if action == "idle":
        return EconomicDecision("idle", 0.0, 0.0, 0.0, "idle is highest allowed action")
    return EconomicDecision(
        chosen_action=action,
        expected_qi=round(expected_qi, 12),
        expected_cost=round(expected_cost, 12),
        expected_profit=round(expected_profit, 12),
        reasoning=f"{action} selected by highest deterministic expected profit",
    )


def _opportunity(
    data: dict[str, Any],
    *,
    qi_key: str,
    cost_key: str,
    profit_key: str,
    default_qi_key: str | None = None,
) -> tuple[float, float, float]:
    qi = float(data.get(qi_key, data.get(default_qi_key, 0.0) if default_qi_key else 0.0))
    cost = float(data.get(cost_key, 0.0))
    profit = float(data.get(profit_key, qi - cost))
    return (qi, cost, profit)


def _action_rank(action: str) -> int:
    return {
        "serve_inference": 5,
        "verify": 4,
        "route": 3,
        "mine": 2,
        "idle": 1,
    }.get(action, 0)
