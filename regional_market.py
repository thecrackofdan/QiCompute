from __future__ import annotations

from typing import Any


REGIONS = ("Atlantic Canada", "US East", "US West", "Europe", "Asia")


def simulate_regional_market(cycles: int = 100) -> dict[str, Any]:
    regional = {}
    total_cross_region = 0.0
    total_jobs = 0.0
    for index, region in enumerate(REGIONS):
        power_cost = 0.012 + index * 0.002
        worker_supply = 2 + index
        privacy_preference = 0.8 if region in {"Atlantic Canada", "Europe"} else 0.55
        jobs = 0.0
        profit = 0.0
        mining_fallbacks = 0.0
        cross_region = 0.0
        for cycle in range(max(int(cycles), 0)):
            demand = ((cycle + index * 3) % 11) + index
            mining_profit = max(0.004 - power_cost * 0.08, 0.0005)
            inference_profit = demand * (0.0012 + privacy_preference * 0.0004) - worker_supply * power_cost * 0.0003
            if inference_profit > mining_profit:
                served = min(demand, worker_supply + 2)
                jobs += served
                profit += inference_profit
                if demand > worker_supply + 2:
                    cross_region += demand - served
            else:
                mining_fallbacks += 1
                profit += mining_profit
        total_cross_region += cross_region
        total_jobs += jobs
        regional[region] = {
            "regional_job_volume": round(jobs, 12),
            "regional_profitability": round(profit, 12),
            "regional_mining_fallback_ratio": round(mining_fallbacks / max(cycles, 1), 12),
            "cross_region_routing_rate": round(cross_region / max(jobs + cross_region, 1.0), 12),
            "privacy_preference": privacy_preference,
        }
    return {
        "cycles": cycles,
        "regions": regional,
        "regional_job_volume": round(total_jobs, 12),
        "cross_region_routing_rate": round(total_cross_region / max(total_jobs + total_cross_region, 1.0), 12),
    }
