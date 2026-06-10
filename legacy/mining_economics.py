from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MiningEconomics:
    expected_qi_per_hour: float
    expected_cost_per_hour: float
    expected_profit_per_hour: float

    def to_dict(self) -> dict[str, float]:
        return {
            "expected_qi_per_hour": self.expected_qi_per_hour,
            "expected_cost_per_hour": self.expected_cost_per_hour,
            "expected_profit_per_hour": self.expected_profit_per_hour,
        }


def estimate_mining_opportunity(
    *,
    gpu_count: int,
    hash_rate_per_gpu: float,
    network_difficulty: float,
    power_watts: float,
    energy_cost_per_kwh: float,
    expected_block_reward_qi: float,
) -> MiningEconomics:
    difficulty = max(float(network_difficulty), 1.0)
    gpu_count = max(int(gpu_count), 0)
    total_hash_rate = gpu_count * max(float(hash_rate_per_gpu), 0.0)
    expected_blocks_per_hour = total_hash_rate / difficulty
    qi_per_hour = expected_blocks_per_hour * max(float(expected_block_reward_qi), 0.0)
    kwh_per_hour = max(float(power_watts), 0.0) * gpu_count / 1000.0
    cost_per_hour = kwh_per_hour * max(float(energy_cost_per_kwh), 0.0)
    return MiningEconomics(
        expected_qi_per_hour=round(qi_per_hour, 12),
        expected_cost_per_hour=round(cost_per_hour, 12),
        expected_profit_per_hour=round(qi_per_hour - cost_per_hour, 12),
    )
