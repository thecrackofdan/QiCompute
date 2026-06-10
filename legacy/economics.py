from __future__ import annotations

from typing import Any


def compare_inference_vs_mining(
    *,
    gpu_wattage: float,
    energy_cost_per_kwh: float,
    inference_utilization: float,
    mining_reward_estimate_qi_per_hour: float,
    average_inference_price_qi: float,
    tokens_per_second: float,
) -> dict[str, Any]:
    utilization = max(0.0, min(float(inference_utilization), 1.0))
    idle = 1.0 - utilization
    tokens_per_hour = max(float(tokens_per_second), 0.0) * 3600.0 * utilization
    inference_jobs_per_hour = tokens_per_hour / 1000.0
    inference_revenue = inference_jobs_per_hour * max(float(average_inference_price_qi), 0.0)
    mining_revenue = idle * max(float(mining_reward_estimate_qi_per_hour), 0.0)
    energy_cost = (max(float(gpu_wattage), 0.0) / 1000.0) * max(float(energy_cost_per_kwh), 0.0)
    total_revenue = inference_revenue + mining_revenue
    return {
        "estimated_inference_revenue_qi_per_hour": round(inference_revenue, 12),
        "estimated_mining_fallback_revenue_qi_per_hour": round(mining_revenue, 12),
        "energy_cost_per_hour": round(energy_cost, 12),
        "utilization_ratio": round(utilization, 6),
        "idle_capacity_ratio": round(idle, 6),
        "efficiency_score": round(total_revenue / energy_cost, 12) if energy_cost > 0 else 0.0,
    }
