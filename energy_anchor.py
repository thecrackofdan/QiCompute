from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from typing import Any


JOULES_PER_KWH = 3_600_000.0
SECONDS_PER_HOUR = 3_600.0


@dataclass(frozen=True)
class EnergyParity:
    qi_per_joule: float
    qi_per_kwh: float
    joules_per_qi: float
    basis: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "qi_per_joule": self.qi_per_joule,
            "qi_per_kwh": self.qi_per_kwh,
            "joules_per_qi": self.joules_per_qi,
            "basis": self.basis,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class EnergyAnchoredPrice:
    energy_joules: float
    anchored_price_qi: float
    token_price_qi: float
    premium_over_energy_parity: float
    qi_per_joule: float
    pricing_basis: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "energy_joules": self.energy_joules,
            "anchored_price_qi": self.anchored_price_qi,
            "token_price_qi": self.token_price_qi,
            "premium_over_energy_parity": self.premium_over_energy_parity,
            "qi_per_joule": self.qi_per_joule,
            "pricing_basis": self.pricing_basis,
            "metadata": self.metadata,
        }


def mining_energy_parity(*, mining_qi_per_hour: float, power_watts: float) -> EnergyParity:
    """Exchange rate between energy and Qi implied by mining issuance.

    Mining is the only issuance path, so the Qi a rig mints per hour divided by
    the joules it burns per hour is the marketplace's observable energy price of
    Qi. Inference jobs measured in joules can be priced against this rate.
    """
    qi_per_hour = max(float(mining_qi_per_hour), 0.0)
    watts = max(float(power_watts), 0.0)
    joules_per_hour = watts * SECONDS_PER_HOUR
    qi_per_joule = qi_per_hour / joules_per_hour if joules_per_hour > 0 else 0.0
    return EnergyParity(
        qi_per_joule=round(qi_per_joule, 18),
        qi_per_kwh=round(qi_per_joule * JOULES_PER_KWH, 12),
        joules_per_qi=round(1.0 / qi_per_joule, 6) if qi_per_joule > 0 else 0.0,
        basis="mining_issuance",
        metadata={
            "mining_qi_per_hour": qi_per_hour,
            "power_watts": watts,
            "joules_per_hour": joules_per_hour,
        },
    )


def joules_per_token(*, energy_joules: float, tokens: float) -> float:
    output = max(float(tokens), 0.0)
    if output <= 0:
        return 0.0
    return round(max(float(energy_joules), 0.0) / output, 12)


def energy_anchored_price(
    *,
    energy_joules: float,
    qi_per_joule: float,
    overhead_multiplier: float = 1.2,
    token_price_qi: float = 0.0,
) -> EnergyAnchoredPrice:
    """Price an inference job from its measured energy at the parity rate.

    The anchored price is the Qi the same joules would have minted through
    mining, marked up by an overhead multiplier covering verification, routing,
    and operator margin. ``premium_over_energy_parity`` reports how the
    token-based quote compares: above 1.0 means inference pays more Qi per
    joule than mining issues, which is the rational condition for serving jobs.
    """
    joules = max(float(energy_joules), 0.0)
    rate = max(float(qi_per_joule), 0.0)
    overhead = max(float(overhead_multiplier), 1.0)
    token_price = max(float(token_price_qi), 0.0)
    anchored = joules * rate * overhead
    premium = token_price / anchored if anchored > 0 else 0.0
    return EnergyAnchoredPrice(
        energy_joules=round(joules, 8),
        anchored_price_qi=round(anchored, 12),
        token_price_qi=round(token_price, 12),
        premium_over_energy_parity=round(premium, 12),
        qi_per_joule=round(rate, 18),
        pricing_basis="energy_parity*overhead",
        metadata={"overhead_multiplier": overhead},
    )


def derive_energy_rate(config: dict[str, Any]) -> float:
    """Resolve ``energy_rate_qi_per_joule`` for pricing from configuration.

    When the ``energy_anchor`` section is enabled, the rate is derived from the
    configured mining reference rig instead of the static pricing value, so the
    energy component of job prices tracks the mining parity rate.
    """
    anchor_cfg = config.get("energy_anchor", {})
    static_rate = max(float(config.get("pricing", {}).get("energy_rate_qi_per_joule", 0.0)), 0.0)
    if not anchor_cfg.get("enabled", False):
        return static_rate
    parity = mining_energy_parity(
        mining_qi_per_hour=float(anchor_cfg.get("reference_mining_qi_per_hour", 0.0)),
        power_watts=float(anchor_cfg.get("reference_power_watts", 0.0)),
    )
    worker_share = min(max(float(anchor_cfg.get("worker_share", 1.0)), 0.0), 1.0)
    return round(parity.qi_per_joule * worker_share, 18)


def epoch_energy_report(epoch_summary: dict[str, Any], *, parity: EnergyParity | None = None) -> dict[str, Any]:
    """Energy accounting for a finalized epoch.

    Reports how much Qi the epoch settled per joule of verified work and, when
    a mining parity rate is supplied, whether inference paid above or below the
    rate at which the same energy would have minted Qi.
    """
    total_joules = max(float(epoch_summary.get("total_energy_joules", 0.0)), 0.0)
    settled_qi = max(float(epoch_summary.get("total_settled_qi", 0.0)), 0.0)
    total_tokens = max(float(epoch_summary.get("total_tokens", 0.0)), 0.0)
    settled_qi_per_joule = settled_qi / total_joules if total_joules > 0 else 0.0
    report: dict[str, Any] = {
        "epoch_id": epoch_summary.get("epoch_id"),
        "total_energy_joules": round(total_joules, 8),
        "total_settled_qi": round(settled_qi, 12),
        "settled_qi_per_joule": round(settled_qi_per_joule, 18),
        "settled_qi_per_kwh": round(settled_qi_per_joule * JOULES_PER_KWH, 12),
        "joules_per_token": joules_per_token(energy_joules=total_joules, tokens=total_tokens),
    }
    if parity is not None:
        ratio = settled_qi_per_joule / parity.qi_per_joule if parity.qi_per_joule > 0 else 0.0
        report["mining_parity_qi_per_joule"] = parity.qi_per_joule
        report["settlement_vs_mining_parity"] = round(ratio, 12)
        report["energy_verdict"] = "inference_beats_mining_parity" if ratio > 1.0 else "mining_parity_beats_inference"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="QiCompute energy anchor report")
    parser.add_argument("--mining-qi-per-hour", type=float, default=0.05)
    parser.add_argument("--power-watts", type=float, default=250.0)
    parser.add_argument("--job-energy-joules", type=float, default=750.0)
    parser.add_argument("--job-token-price-qi", type=float, default=0.0)
    parser.add_argument("--overhead-multiplier", type=float, default=1.2)
    args = parser.parse_args()
    parity = mining_energy_parity(
        mining_qi_per_hour=args.mining_qi_per_hour,
        power_watts=args.power_watts,
    )
    price = energy_anchored_price(
        energy_joules=args.job_energy_joules,
        qi_per_joule=parity.qi_per_joule,
        overhead_multiplier=args.overhead_multiplier,
        token_price_qi=args.job_token_price_qi,
    )
    print(json.dumps({"energy_parity": parity.to_dict(), "anchored_price": price.to_dict()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
