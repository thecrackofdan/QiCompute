from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MarketPrice:
    spot_price_qi: float
    floor_price_qi: float
    premium_price_qi: float
    pricing_reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "spot_price_qi": self.spot_price_qi,
            "floor_price_qi": self.floor_price_qi,
            "premium_price_qi": self.premium_price_qi,
            "pricing_reason": self.pricing_reason,
        }


def compute_market_price(
    *,
    compute_supply: float,
    customer_demand: float,
    worker_utilization: float,
    mining_fallback_profitability: float,
    latency_class: str = "standard",
    privacy_class: str = "standard",
    verification_class: str = "standard",
    regional_scarcity: float = 0.0,
) -> MarketPrice:
    supply = max(float(compute_supply), 1.0)
    demand = max(float(customer_demand), 0.0)
    utilization = min(max(float(worker_utilization), 0.0), 1.0)
    mining_floor = max(float(mining_fallback_profitability), 0.0)
    floor_price = mining_floor * 1.05
    pressure = demand / supply
    premium = (
        floor_price * max(pressure - 0.5, 0.0) * 0.55
        + floor_price * utilization * 0.35
        + _class_premium(latency_class, {"standard": 0.0, "low_latency": 0.18, "urgent": 0.34})
        + _class_premium(privacy_class, {"standard": 0.0, "private": 0.16, "confidential": 0.30})
        + _class_premium(verification_class, {"standard": 0.0, "verified": 0.14, "audited": 0.24})
        + floor_price * max(float(regional_scarcity), 0.0) * 0.25
    )
    spot = max(floor_price, floor_price + premium)
    return MarketPrice(
        spot_price_qi=round(spot, 12),
        floor_price_qi=round(floor_price, 12),
        premium_price_qi=round(premium, 12),
        pricing_reason=(
            "mining fallback sets the floor; demand, utilization, service class, "
            "verification, privacy, and regional scarcity set the premium"
        ),
    )


def _class_premium(value: str, table: dict[str, float]) -> float:
    return float(table.get(value, 0.0))
