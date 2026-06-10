from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from typing import Any

from energy_peg import EnergyQuote, quote_job_in_energy


DEFAULT_REFERENCE_JOULES_PER_TOKEN = 3.0
DEFAULT_RECALIBRATION_ALPHA = 0.2
DEFAULT_RECALIBRATION_MAX_STEP_RATIO = 0.1


@dataclass(frozen=True)
class EfficiencyMargin:
    reference_joules: float
    measured_joules: float
    efficiency_ratio: float
    margin_joules: float
    margin_qi: float
    verdict: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_joules": self.reference_joules,
            "measured_joules": self.measured_joules,
            "efficiency_ratio": self.efficiency_ratio,
            "margin_joules": self.margin_joules,
            "margin_qi": self.margin_qi,
            "verdict": self.verdict,
            "metadata": self.metadata,
        }


def reference_joules_per_token(model: str, config: dict[str, Any]) -> float:
    """Benchmark joules-per-token for a model class.

    Billing against a reference rather than a worker's measured draw is what
    keeps energy pricing from becoming cost-plus: the price of a job depends
    on the work (model and tokens), not on how wastefully a particular rig
    produced it.
    """
    table = config.get("energy_anchor", {}).get("reference_joules_per_token", {})
    if isinstance(table, dict):
        value = table.get(model, table.get("default", DEFAULT_REFERENCE_JOULES_PER_TOKEN))
    else:
        value = table
    return max(float(value), 0.0)


def standardized_job_joules(*, model: str, output_tokens: float, config: dict[str, Any]) -> float:
    return round(max(float(output_tokens), 0.0) * reference_joules_per_token(model, config), 8)


def standardized_energy_quote(
    *,
    model: str,
    output_tokens: float,
    parity_qi_per_joule: float,
    config: dict[str, Any],
    overhead_multiplier: float = 1.2,
    privacy_class: str = "standard",
    latency_class: str = "standard",
) -> EnergyQuote:
    """Quote a job at the benchmark energy for its model class.

    Two workers serving the same job receive the same quote regardless of
    their measured draw. An efficient rig completes the work under the
    benchmark and keeps the difference as margin; an inefficient rig eats it.
    Metered output is settled, the way electricity markets settle delivered
    power rather than fuel burned.
    """
    reference_joules = standardized_job_joules(model=model, output_tokens=output_tokens, config=config)
    quote = quote_job_in_energy(
        energy_joules=reference_joules,
        parity_qi_per_joule=parity_qi_per_joule,
        overhead_multiplier=overhead_multiplier,
        privacy_class=privacy_class,
        latency_class=latency_class,
    )
    metadata = dict(quote.metadata)
    metadata.update(
        {
            "model": model,
            "output_tokens": max(float(output_tokens), 0.0),
            "reference_joules_per_token": reference_joules_per_token(model, config),
            "billing_basis": "reference_joules",
        }
    )
    return EnergyQuote(
        price_joules=quote.price_joules,
        parity_qi_per_joule=quote.parity_qi_per_joule,
        settlement_qi=quote.settlement_qi,
        pricing_basis="reference_joules*overhead*service_class -> qi_at_parity",
        metadata=metadata,
    )


def efficiency_margin(
    *,
    reference_joules: float,
    measured_joules: float,
    parity_qi_per_joule: float,
) -> EfficiencyMargin:
    """Worker margin from beating (or missing) the energy benchmark.

    The job pays for reference joules; the worker spends measured joules.
    A positive margin is the efficiency premium an operator earns by running
    better hardware or tighter inference than the benchmark assumes.
    """
    reference = max(float(reference_joules), 0.0)
    measured = max(float(measured_joules), 0.0)
    rate = max(float(parity_qi_per_joule), 0.0)
    margin = reference - measured
    return EfficiencyMargin(
        reference_joules=round(reference, 8),
        measured_joules=round(measured, 8),
        efficiency_ratio=round(reference / measured, 12) if measured > 0 else 0.0,
        margin_joules=round(margin, 8),
        margin_qi=round(margin * rate, 12),
        verdict="efficiency_premium" if margin >= 0 else "efficiency_penalty",
    )


def worker_efficiency_report(
    worker: dict[str, Any],
    *,
    model: str,
    config: dict[str, Any],
    parity_qi_per_joule: float,
) -> dict[str, Any]:
    """Compare a worker's tracked average energy-per-token to the benchmark."""
    measured_per_token = max(float(worker.get("average_energy_per_token", 0.0)), 0.0)
    reference_per_token = reference_joules_per_token(model, config)
    margin = efficiency_margin(
        reference_joules=reference_per_token,
        measured_joules=measured_per_token,
        parity_qi_per_joule=parity_qi_per_joule,
    )
    return {
        "worker_id": worker.get("worker_id"),
        "model": model,
        "reference_joules_per_token": reference_per_token,
        "measured_joules_per_token": measured_per_token,
        "margin_qi_per_token": margin.margin_qi,
        "efficiency_ratio": margin.efficiency_ratio,
        "verdict": margin.verdict if measured_per_token > 0 else "unmeasured",
    }


def recalibrate_reference(
    *,
    current_reference: float,
    observed_fleet_joules_per_token: float,
    adjustment_alpha: float = DEFAULT_RECALIBRATION_ALPHA,
    max_step_ratio: float = DEFAULT_RECALIBRATION_MAX_STEP_RATIO,
) -> dict[str, Any]:
    """Drift the benchmark toward observed fleet efficiency, with a clamp.

    As hardware improves, fleet joules-per-token falls; the benchmark should
    follow so efficiency gains eventually reach customers instead of staying
    operator margin forever. The clamped step keeps the ratchet gradual, so
    workers retain a near-term incentive to beat the current benchmark.
    """
    current = max(float(current_reference), 0.0)
    observed = max(float(observed_fleet_joules_per_token), 0.0)
    alpha = min(max(float(adjustment_alpha), 0.0), 1.0)
    max_step = max(float(max_step_ratio), 0.0)
    blended = alpha * observed + (1.0 - alpha) * current
    lower = current * (1.0 - max_step)
    upper = current * (1.0 + max_step)
    clamped_value = min(max(blended, lower), upper)
    return {
        "previous_reference": round(current, 8),
        "observed_fleet_joules_per_token": round(observed, 8),
        "new_reference": round(clamped_value, 8),
        "clamped": clamped_value != blended,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="QiCompute standardized energy billing report")
    parser.add_argument("--model", default="llama-3.1-8b")
    parser.add_argument("--output-tokens", type=float, default=500)
    parser.add_argument("--parity-qi-per-joule", type=float, default=5.5555555556e-08)
    parser.add_argument("--measured-joules-per-token", type=float, default=2.4)
    parser.add_argument("--reference-joules-per-token", type=float, default=DEFAULT_REFERENCE_JOULES_PER_TOKEN)
    args = parser.parse_args()
    config = {
        "energy_anchor": {
            "reference_joules_per_token": {"default": args.reference_joules_per_token}
        }
    }
    quote = standardized_energy_quote(
        model=args.model,
        output_tokens=args.output_tokens,
        parity_qi_per_joule=args.parity_qi_per_joule,
        config=config,
    )
    margin = efficiency_margin(
        reference_joules=standardized_job_joules(model=args.model, output_tokens=args.output_tokens, config=config),
        measured_joules=args.measured_joules_per_token * args.output_tokens,
        parity_qi_per_joule=args.parity_qi_per_joule,
    )
    print(json.dumps({"standardized_quote": quote.to_dict(), "efficiency_margin": margin.to_dict()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
