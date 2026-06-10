from __future__ import annotations

from typing import Any


def build_economy_report(metrics: dict[str, Any]) -> dict[str, float]:
    agents = max(int(metrics.get("agent_count", 0)), 1)
    mining_volume = float(metrics.get("mining_volume", metrics.get("mined_qi", 0.0)))
    inference_volume = float(metrics.get("inference_volume", 0.0))
    idle_cycles = float(metrics.get("idle_cycles", 0.0))
    total_cycles = max(float(metrics.get("total_cycles", 0.0)), 1.0)
    total_profit = float(metrics.get("total_profit", 0.0))
    total_qi_mined = float(metrics.get("mined_qi", 0.0))
    total_qi_transferred = float(metrics.get("earned_qi", 0.0)) + float(metrics.get("spent_qi", 0.0))
    ratio_denominator = mining_volume + inference_volume
    return {
        "total_qi_mined": round(total_qi_mined, 12),
        "total_qi_transferred": round(total_qi_transferred, 12),
        "total_inference_volume": round(inference_volume, 12),
        "total_verification_volume": round(float(metrics.get("verification_volume", 0.0)), 12),
        "average_agent_profitability": round(total_profit / agents, 12),
        "mining_inference_ratio": round(mining_volume / ratio_denominator if ratio_denominator else 0.0, 12),
        "idle_capacity_ratio": round(idle_cycles / total_cycles, 12),
    }
