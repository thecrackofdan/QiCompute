from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RealCrossoverResult:
    mining_profit_per_hour: float
    inference_profit_per_hour: float
    crossover_utilization: float
    crossover_threshold_requests_per_hour: float
    profitability_ratio: float
    preferred_action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mining_profit_per_hour": self.mining_profit_per_hour,
            "inference_profit_per_hour": self.inference_profit_per_hour,
            "crossover_utilization": self.crossover_utilization,
            "crossover_threshold_requests_per_hour": self.crossover_threshold_requests_per_hour,
            "profitability_ratio": self.profitability_ratio,
            "preferred_action": self.preferred_action,
        }


def measure_real_crossover(
    *,
    mining_revenue_qi_per_hour: float,
    inference_throughput_requests_per_hour: float,
    qi_per_inference_request: float,
    power_watts: float,
    power_cost_per_kwh: float,
    verification_cost_qi_per_request: float,
    marketplace_fee_percent: float,
    utilization: float = 1.0,
) -> RealCrossoverResult:
    energy_cost_per_hour = max(float(power_watts), 0.0) / 1000.0 * max(float(power_cost_per_kwh), 0.0)
    mining_profit = max(float(mining_revenue_qi_per_hour), 0.0) - energy_cost_per_hour
    throughput = max(float(inference_throughput_requests_per_hour), 0.0)
    fee_multiplier = max(0.0, 1.0 - max(float(marketplace_fee_percent), 0.0) / 100.0)
    net_qi_per_request = max(float(qi_per_inference_request), 0.0) * fee_multiplier - max(float(verification_cost_qi_per_request), 0.0)
    active_requests = throughput * min(max(float(utilization), 0.0), 1.0)
    inference_profit = active_requests * net_qi_per_request - energy_cost_per_hour
    threshold_requests = (mining_profit + energy_cost_per_hour) / net_qi_per_request if net_qi_per_request > 0 else float("inf")
    crossover_utilization = threshold_requests / throughput if throughput > 0 and threshold_requests != float("inf") else float("inf")
    ratio = inference_profit / mining_profit if mining_profit > 0 else float("inf")
    return RealCrossoverResult(
        mining_profit_per_hour=round(mining_profit, 12),
        inference_profit_per_hour=round(inference_profit, 12),
        crossover_utilization=round(crossover_utilization, 12) if crossover_utilization != float("inf") else crossover_utilization,
        crossover_threshold_requests_per_hour=round(threshold_requests, 12) if threshold_requests != float("inf") else threshold_requests,
        profitability_ratio=round(ratio, 12) if ratio != float("inf") else ratio,
        preferred_action="serve_inference" if inference_profit > mining_profit else "mine",
    )
