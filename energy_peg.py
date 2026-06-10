from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from typing import Any

from energy_anchor import mining_energy_parity


PRIVACY_JOULE_MULTIPLIERS = {"standard": 1.0, "private": 1.16, "confidential": 1.30}
LATENCY_JOULE_MULTIPLIERS = {"standard": 1.0, "low_latency": 1.18, "urgent": 1.34}

DEFAULT_SMOOTHING_ALPHA = 0.2
DEFAULT_MAX_STEP_RATIO = 0.1
DEFAULT_CORRIDOR_CEILING_MULTIPLIER = 1.5
DEFAULT_STABLE_CV_THRESHOLD = 0.15


@dataclass(frozen=True)
class ParityOracle:
    qi_per_joule: float
    observation_count: int
    smoothing_alpha: float
    max_step_ratio: float
    last_observed_qi_per_joule: float
    clamped: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "qi_per_joule": self.qi_per_joule,
            "observation_count": self.observation_count,
            "smoothing_alpha": self.smoothing_alpha,
            "max_step_ratio": self.max_step_ratio,
            "last_observed_qi_per_joule": self.last_observed_qi_per_joule,
            "clamped": self.clamped,
        }


@dataclass(frozen=True)
class EnergyQuote:
    price_joules: float
    parity_qi_per_joule: float
    settlement_qi: float
    pricing_basis: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "price_joules": self.price_joules,
            "parity_qi_per_joule": self.parity_qi_per_joule,
            "settlement_qi": self.settlement_qi,
            "pricing_basis": self.pricing_basis,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class CorridorPrice:
    spot_price_qi: float
    floor_price_qi: float
    ceiling_price_qi: float
    clamped: bool
    shed_premium_qi: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "spot_price_qi": self.spot_price_qi,
            "floor_price_qi": self.floor_price_qi,
            "ceiling_price_qi": self.ceiling_price_qi,
            "clamped": self.clamped,
            "shed_premium_qi": self.shed_premium_qi,
        }


def init_parity_oracle(
    *,
    qi_per_joule: float,
    smoothing_alpha: float = DEFAULT_SMOOTHING_ALPHA,
    max_step_ratio: float = DEFAULT_MAX_STEP_RATIO,
) -> ParityOracle:
    return ParityOracle(
        qi_per_joule=round(max(float(qi_per_joule), 0.0), 18),
        observation_count=1,
        smoothing_alpha=min(max(float(smoothing_alpha), 0.0), 1.0),
        max_step_ratio=max(float(max_step_ratio), 0.0),
        last_observed_qi_per_joule=round(max(float(qi_per_joule), 0.0), 18),
        clamped=False,
    )


def update_parity_oracle(oracle: ParityOracle, observed_qi_per_joule: float) -> ParityOracle:
    """Fold one observed Qi-per-joule rate into the smoothed parity rate.

    The published rate is an exponential moving average of observations, and a
    single update can move it by at most ``max_step_ratio`` relative to the
    previous rate. A spike in observed rates (demand surge, mining difficulty
    shock, thin settlement volume) therefore bleeds into the published rate
    over several epochs instead of repricing the marketplace at once.
    """
    observed = max(float(observed_qi_per_joule), 0.0)
    alpha = oracle.smoothing_alpha
    blended = alpha * observed + (1.0 - alpha) * oracle.qi_per_joule
    lower = oracle.qi_per_joule * (1.0 - oracle.max_step_ratio)
    upper = oracle.qi_per_joule * (1.0 + oracle.max_step_ratio)
    clamped_rate = min(max(blended, lower), upper)
    return ParityOracle(
        qi_per_joule=round(clamped_rate, 18),
        observation_count=oracle.observation_count + 1,
        smoothing_alpha=oracle.smoothing_alpha,
        max_step_ratio=oracle.max_step_ratio,
        last_observed_qi_per_joule=round(observed, 18),
        clamped=clamped_rate != blended,
    )


def oracle_from_epoch_summaries(
    summaries: list[dict[str, Any]],
    *,
    initial_qi_per_joule: float,
    smoothing_alpha: float = DEFAULT_SMOOTHING_ALPHA,
    max_step_ratio: float = DEFAULT_MAX_STEP_RATIO,
) -> ParityOracle:
    """Replay finalized epochs into a smoothed parity rate.

    Each epoch's observed rate is ``settled_qi_per_joule`` from its
    ``energy_totals`` metadata; epochs that settled no energy are skipped.
    """
    oracle = init_parity_oracle(
        qi_per_joule=initial_qi_per_joule,
        smoothing_alpha=smoothing_alpha,
        max_step_ratio=max_step_ratio,
    )
    for summary in summaries:
        observed = float(summary.get("metadata", {}).get("energy_totals", {}).get("settled_qi_per_joule", 0.0))
        if observed > 0:
            oracle = update_parity_oracle(oracle, observed)
    return oracle


def quote_job_in_energy(
    *,
    energy_joules: float,
    parity_qi_per_joule: float,
    overhead_multiplier: float = 1.2,
    privacy_class: str = "standard",
    latency_class: str = "standard",
) -> EnergyQuote:
    """Quote a job in joules and convert to Qi only at settlement.

    The customer-facing price is denominated in energy: measured joules marked
    up by overhead and service-class multipliers. That number is invariant to
    Qi volatility. The Qi owed at settlement is the joule price converted at
    the smoothed parity rate, so token swings change the conversion, never the
    energy price of the work.
    """
    joules = max(float(energy_joules), 0.0)
    overhead = max(float(overhead_multiplier), 1.0)
    privacy_mult = PRIVACY_JOULE_MULTIPLIERS.get(privacy_class, 1.0)
    latency_mult = LATENCY_JOULE_MULTIPLIERS.get(latency_class, 1.0)
    rate = max(float(parity_qi_per_joule), 0.0)
    price_joules = joules * overhead * privacy_mult * latency_mult
    return EnergyQuote(
        price_joules=round(price_joules, 8),
        parity_qi_per_joule=round(rate, 18),
        settlement_qi=round(price_joules * rate, 12),
        pricing_basis="joules*overhead*service_class -> qi_at_parity",
        metadata={
            "energy_joules": joules,
            "overhead_multiplier": overhead,
            "privacy_class": privacy_class,
            "latency_class": latency_class,
            "privacy_multiplier": privacy_mult,
            "latency_multiplier": latency_mult,
        },
    )


def apply_stability_corridor(
    *,
    spot_price_qi: float,
    floor_price_qi: float,
    ceiling_multiplier: float = DEFAULT_CORRIDOR_CEILING_MULTIPLIER,
) -> CorridorPrice:
    """Bound a spot price inside [floor, floor * ceiling_multiplier].

    The floor is the energy reservation price (mining fallback). The ceiling
    caps how much demand premium passes to customers in a single quote, so
    scarcity raises prices within a known band instead of without limit.
    """
    floor = max(float(floor_price_qi), 0.0)
    ceiling = floor * max(float(ceiling_multiplier), 1.0)
    spot = max(float(spot_price_qi), 0.0)
    bounded = min(max(spot, floor), ceiling)
    return CorridorPrice(
        spot_price_qi=round(bounded, 12),
        floor_price_qi=round(floor, 12),
        ceiling_price_qi=round(ceiling, 12),
        clamped=bounded != spot,
        shed_premium_qi=round(max(spot - ceiling, 0.0), 12),
    )


def price_stability_report(
    rates: list[float],
    *,
    stable_cv_threshold: float = DEFAULT_STABLE_CV_THRESHOLD,
) -> dict[str, Any]:
    """Volatility metrics for a Qi-per-joule (or price) series.

    The verdict is "stable" when the coefficient of variation is at or below
    the threshold; the max step ratio reports the worst single-period move.
    """
    values = [max(float(rate), 0.0) for rate in rates]
    count = len(values)
    mean = sum(values) / count if count else 0.0
    variance = sum((value - mean) ** 2 for value in values) / count if count else 0.0
    stdev = variance ** 0.5
    cv = stdev / mean if mean > 0 else 0.0
    max_step = 0.0
    for previous, current in zip(values, values[1:]):
        if previous > 0:
            max_step = max(max_step, abs(current - previous) / previous)
    return {
        "sample_count": count,
        "mean": round(mean, 18),
        "stdev": round(stdev, 18),
        "coefficient_of_variation": round(cv, 12),
        "max_step_ratio": round(max_step, 12),
        "stable_cv_threshold": float(stable_cv_threshold),
        "verdict": "stable" if cv <= float(stable_cv_threshold) else "volatile",
    }


def simulate_peg_stability(
    *,
    cycles: int = 60,
    base_qi_per_joule: float = 5.5555555556e-08,
    job_energy_joules: float = 750.0,
    smoothing_alpha: float = DEFAULT_SMOOTHING_ALPHA,
    max_step_ratio: float = DEFAULT_MAX_STEP_RATIO,
    stable_cv_threshold: float = DEFAULT_STABLE_CV_THRESHOLD,
) -> dict[str, Any]:
    """Deterministic comparison of raw token pricing against the energy peg.

    The observed Qi-per-joule rate swings through a fixed boom/bust pattern.
    Raw pricing converts every job at the observed rate; pegged pricing quotes
    the same jobs in joules and converts at the smoothed oracle rate. The
    report compares the volatility of the two Qi cost series; the joule price
    itself never moves.
    """
    oracle = init_parity_oracle(
        qi_per_joule=base_qi_per_joule,
        smoothing_alpha=smoothing_alpha,
        max_step_ratio=max_step_ratio,
    )
    raw_costs: list[float] = []
    pegged_costs: list[float] = []
    clamped_updates = 0
    for cycle in range(max(int(cycles), 0)):
        observed_rate = base_qi_per_joule * _rate_swing(cycle)
        oracle = update_parity_oracle(oracle, observed_rate)
        if oracle.clamped:
            clamped_updates += 1
        raw_costs.append(job_energy_joules * observed_rate)
        pegged_costs.append(quote_job_in_energy(
            energy_joules=job_energy_joules,
            parity_qi_per_joule=oracle.qi_per_joule,
            overhead_multiplier=1.0,
        ).settlement_qi)
    raw_report = price_stability_report(raw_costs, stable_cv_threshold=stable_cv_threshold)
    pegged_report = price_stability_report(pegged_costs, stable_cv_threshold=stable_cv_threshold)
    raw_cv = raw_report["coefficient_of_variation"]
    pegged_cv = pegged_report["coefficient_of_variation"]
    return {
        "cycles": cycles,
        "job_price_joules": round(job_energy_joules, 8),
        "raw_token_pricing": raw_report,
        "energy_pegged_pricing": pegged_report,
        "volatility_reduction_ratio": round(1.0 - pegged_cv / raw_cv, 12) if raw_cv > 0 else 0.0,
        "clamped_oracle_updates": clamped_updates,
        "final_oracle": oracle.to_dict(),
    }


def peg_settings(config: dict[str, Any]) -> dict[str, float]:
    anchor_cfg = config.get("energy_anchor", {})
    return {
        "smoothing_alpha": float(anchor_cfg.get("smoothing_alpha", DEFAULT_SMOOTHING_ALPHA)),
        "max_step_ratio": float(anchor_cfg.get("max_step_ratio", DEFAULT_MAX_STEP_RATIO)),
        "corridor_ceiling_multiplier": float(
            anchor_cfg.get("corridor_ceiling_multiplier", DEFAULT_CORRIDOR_CEILING_MULTIPLIER)
        ),
        "stable_cv_threshold": float(anchor_cfg.get("stable_cv_threshold", DEFAULT_STABLE_CV_THRESHOLD)),
    }


def _rate_swing(cycle: int) -> float:
    phase = cycle % 20
    if phase < 4:
        return 1.0
    if phase < 8:
        return 1.45
    if phase < 12:
        return 0.65
    if phase < 16:
        return 1.7
    return 0.8


def main() -> int:
    parser = argparse.ArgumentParser(description="QiCompute energy peg stability report")
    parser.add_argument("--cycles", type=int, default=60)
    parser.add_argument("--mining-qi-per-hour", type=float, default=0.05)
    parser.add_argument("--power-watts", type=float, default=250.0)
    parser.add_argument("--job-energy-joules", type=float, default=750.0)
    parser.add_argument("--smoothing-alpha", type=float, default=DEFAULT_SMOOTHING_ALPHA)
    parser.add_argument("--max-step-ratio", type=float, default=DEFAULT_MAX_STEP_RATIO)
    args = parser.parse_args()
    parity = mining_energy_parity(
        mining_qi_per_hour=args.mining_qi_per_hour,
        power_watts=args.power_watts,
    )
    report = simulate_peg_stability(
        cycles=args.cycles,
        base_qi_per_joule=parity.qi_per_joule,
        job_energy_joules=args.job_energy_joules,
        smoothing_alpha=args.smoothing_alpha,
        max_step_ratio=args.max_step_ratio,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
