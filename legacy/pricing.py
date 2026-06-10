from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from energy_anchor import derive_energy_rate


@dataclass(frozen=True)
class PriceEstimate:
    estimated_price_qi: float
    pricing_basis: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "estimated_price_qi": self.estimated_price_qi,
            "pricing_basis": self.pricing_basis,
            "metadata": self.metadata,
        }


def estimate_job_price(
    *,
    input_tokens: float,
    output_tokens: float,
    model: str,
    privacy_level: str,
    latency_target: float | None,
    energy_joules: float,
    worker_reputation: float,
    config: dict[str, Any],
) -> PriceEstimate:
    pricing_cfg = config.get("pricing", {})
    input_rate = float(pricing_cfg.get("base_input_token_rate_qi", 0.00000005))
    output_rate = float(pricing_cfg.get("base_output_token_rate_qi", 0.0000002))
    privacy_multiplier = float(pricing_cfg.get("privacy_premium_multiplier", 1.25 if privacy_level != "standard" else 1.0))
    latency_multiplier = 1.0
    if latency_target and latency_target <= float(pricing_cfg.get("low_latency_threshold_ms", 2000)):
        latency_multiplier = float(pricing_cfg.get("low_latency_premium_multiplier", 1.15))
    reputation_multiplier = 1.0 + max(worker_reputation - 50, 0) / 1000
    energy_rate = derive_energy_rate(config)

    token_price = input_tokens * input_rate + output_tokens * output_rate
    estimated = token_price * privacy_multiplier * latency_multiplier * reputation_multiplier
    estimated += energy_joules * energy_rate

    return PriceEstimate(
        estimated_price_qi=round(max(estimated, 0.0), 12),
        pricing_basis="tokens+privacy+latency+reputation+energy",
        metadata={
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "privacy_multiplier": privacy_multiplier,
            "latency_multiplier": latency_multiplier,
            "reputation_multiplier": reputation_multiplier,
            "energy_joules": energy_joules,
            "energy_rate_qi_per_joule": energy_rate,
        },
    )
