from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PilotOperator:
    operator_id: str
    role: str
    gpu_profile: str
    worker_count: int
    uptime: float = 0.0
    utilization: float = 0.0
    settlement_volume: float = 0.0
    disputes: int = 0
    profitability: float = 0.0


def run_trusted_operator_pilot(cycles: int = 100) -> dict[str, Any]:
    operators = [
        PilotOperator("operator-a", "inference", "3090", 1),
        PilotOperator("operator-b", "inference", "2x3080", 2),
        PilotOperator("operator-c", "verifier", "cpu-verifier", 0),
    ]
    for cycle in range(max(int(cycles), 0)):
        demand = 1 + (cycle % 6)
        for operator in operators:
            uptime = 1.0 if (cycle + len(operator.operator_id)) % 23 != 0 else 0.0
            operator.uptime += uptime
            if operator.role == "verifier":
                volume = 0.0015 * demand * uptime
                operator.settlement_volume += volume
                operator.profitability += volume - 0.0001
                operator.utilization += min(demand / 6, 1.0) * uptime
            else:
                served = min(demand, max(operator.worker_count, 1)) * uptime
                volume = served * 0.006
                operator.settlement_volume += volume
                operator.profitability += volume - served * 0.001
                operator.utilization += min(served / max(operator.worker_count, 1), 1.0)
            if cycle % 41 == 0 and cycle != 0 and operator.role == "inference":
                operator.disputes += 1
                operator.profitability -= 0.002
    summaries = {
        operator.operator_id: {
            "role": operator.role,
            "gpu_profile": operator.gpu_profile,
            "uptime": round(operator.uptime / max(cycles, 1), 12),
            "utilization": round(operator.utilization / max(cycles, 1), 12),
            "settlement_volume": round(operator.settlement_volume, 12),
            "disputes": operator.disputes,
            "profitability": round(operator.profitability, 12),
        }
        for operator in operators
    }
    return {
        "cycles": cycles,
        "operators": summaries,
        "settlement_volume": round(sum(item["settlement_volume"] for item in summaries.values()), 12),
        "disputes": sum(item["disputes"] for item in summaries.values()),
        "average_uptime": round(sum(item["uptime"] for item in summaries.values()) / len(summaries), 12),
        "average_utilization": round(sum(item["utilization"] for item in summaries.values()) / len(summaries), 12),
        "total_profitability": round(sum(item["profitability"] for item in summaries.values()), 12),
    }
