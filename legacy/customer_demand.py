from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CUSTOMER_TYPES = (
    "privacy_sensitive",
    "cost_sensitive",
    "latency_sensitive",
    "enterprise",
    "agent_customer",
    "bulk_batch",
)

PROVIDERS = ("QiCompute", "centralized_ai_api", "gpu_cloud", "self_hosted")


@dataclass(frozen=True)
class CustomerChoice:
    chosen_provider: str
    reason: str
    willingness_to_pay_qi: float
    sensitivity_scores: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "chosen_provider": self.chosen_provider,
            "reason": self.reason,
            "willingness_to_pay_qi": self.willingness_to_pay_qi,
            "sensitivity_scores": dict(self.sensitivity_scores),
        }


def choose_customer_provider(customer_type: str, providers: dict[str, dict[str, float]]) -> CustomerChoice:
    weights = _weights_for_customer(customer_type)
    scored = []
    for provider in PROVIDERS:
        metrics = providers.get(provider, {})
        score = _score_provider(metrics, weights)
        scored.append((score, provider, metrics))
    score, provider, metrics = max(scored, key=lambda item: (item[0], _provider_rank(item[1])))
    willingness = _willingness_to_pay(customer_type, metrics, score)
    return CustomerChoice(
        chosen_provider=provider,
        reason=_reason(customer_type, provider, metrics, weights),
        willingness_to_pay_qi=round(willingness, 12),
        sensitivity_scores={name: round(value, 6) for name, value in weights.items()},
    )


def _score_provider(metrics: dict[str, float], weights: dict[str, float]) -> float:
    price = max(float(metrics.get("price", 0.0)), 0.0)
    price_score = 1.0 / (1.0 + price)
    latency_score = 1.0 / (1.0 + max(float(metrics.get("latency", 0.0)), 0.0) / 1000.0)
    score = (
        weights["price"] * price_score
        + weights["latency"] * latency_score
        + weights["privacy"] * _clamp(metrics.get("privacy_score", 0.0))
        + weights["reliability"] * _clamp(metrics.get("reliability", 0.0))
        + weights["verification"] * _clamp(metrics.get("verification_score", 0.0))
        + weights["region"] * _clamp(metrics.get("region_match", 0.0))
    )
    return round(score, 12)


def _weights_for_customer(customer_type: str) -> dict[str, float]:
    profiles = {
        "privacy_sensitive": {"price": 0.10, "latency": 0.10, "privacy": 0.34, "reliability": 0.16, "verification": 0.22, "region": 0.08},
        "cost_sensitive": {"price": 0.38, "latency": 0.12, "privacy": 0.10, "reliability": 0.14, "verification": 0.12, "region": 0.14},
        "latency_sensitive": {"price": 0.08, "latency": 0.40, "privacy": 0.10, "reliability": 0.22, "verification": 0.08, "region": 0.12},
        "enterprise": {"price": 0.10, "latency": 0.14, "privacy": 0.20, "reliability": 0.26, "verification": 0.20, "region": 0.10},
        "agent_customer": {"price": 0.22, "latency": 0.16, "privacy": 0.14, "reliability": 0.16, "verification": 0.22, "region": 0.10},
        "bulk_batch": {"price": 0.36, "latency": 0.04, "privacy": 0.14, "reliability": 0.14, "verification": 0.12, "region": 0.20},
    }
    return profiles.get(customer_type, profiles["cost_sensitive"])


def _willingness_to_pay(customer_type: str, metrics: dict[str, float], score: float) -> float:
    base = {
        "privacy_sensitive": 1.25,
        "cost_sensitive": 0.85,
        "latency_sensitive": 1.15,
        "enterprise": 1.4,
        "agent_customer": 1.0,
        "bulk_batch": 0.75,
    }.get(customer_type, 1.0)
    price = max(float(metrics.get("price", 0.0)), 0.0)
    return max(price, price * base * (0.75 + score / 2.0))


def _reason(customer_type: str, provider: str, metrics: dict[str, float], weights: dict[str, float]) -> str:
    strongest = max(weights.items(), key=lambda item: item[1])[0]
    return (
        f"{provider} selected for {customer_type}: strongest sensitivity is {strongest}, "
        f"privacy={float(metrics.get('privacy_score', 0.0)):.3f}, "
        f"verification={float(metrics.get('verification_score', 0.0)):.3f}, "
        f"latency={float(metrics.get('latency', 0.0)):.3f}"
    )


def _provider_rank(provider: str) -> int:
    return {"QiCompute": 4, "self_hosted": 3, "centralized_ai_api": 2, "gpu_cloud": 1}.get(provider, 0)


def _clamp(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)
