from __future__ import annotations

import argparse
import json
from typing import Any

from energy_anchor import mining_energy_parity
from evidence_registry import record_evidence
from hardware_validation import run_hardware_validation
from worker import load_config


DRIFT_WARNING_RATIO = 0.25


def calibrate_from_measurements(
    *,
    tokens_per_second: float,
    power_watts: float,
    mining_qi_per_hour: float,
    config: dict[str, Any],
    model: str = "default",
    gpu_model: str = "unknown-gpu",
    measurement_source: str = "manual",
) -> dict[str, Any]:
    """Turn hardware measurements into the energy model's config inputs.

    The energy model rests on two configured numbers: the reference mining
    rate (Qi issued per hour at a known wattage) and the billing benchmark
    (joules per token per model class). This produces both from measurements,
    compares them against the currently configured values, and flags drift
    beyond ``DRIFT_WARNING_RATIO`` so stale config is visible.
    """
    tps = max(float(tokens_per_second), 0.0)
    watts = max(float(power_watts), 0.0)
    measured_joules_per_token = round(watts / tps, 8) if tps > 0 else 0.0
    parity = mining_energy_parity(mining_qi_per_hour=mining_qi_per_hour, power_watts=watts)

    anchor_cfg = config.get("energy_anchor", {})
    reference_table = anchor_cfg.get("reference_joules_per_token", {})
    configured_joules_per_token = float(
        reference_table.get(model, reference_table.get("default", 0.0)) if isinstance(reference_table, dict) else reference_table
    )
    configured_mining_rate = float(anchor_cfg.get("reference_mining_qi_per_hour", 0.0))
    configured_watts = float(anchor_cfg.get("reference_power_watts", 0.0))

    drift = {
        "reference_joules_per_token": _drift_ratio(configured_joules_per_token, measured_joules_per_token),
        "reference_mining_qi_per_hour": _drift_ratio(configured_mining_rate, max(float(mining_qi_per_hour), 0.0)),
        "reference_power_watts": _drift_ratio(configured_watts, watts),
    }
    warnings = sorted(key for key, ratio in drift.items() if ratio > DRIFT_WARNING_RATIO)

    return {
        "measurement": {
            "source": measurement_source,
            "gpu_model": gpu_model,
            "model": model,
            "tokens_per_second": round(tps, 8),
            "power_watts": round(watts, 8),
            "measured_joules_per_token": measured_joules_per_token,
            "mining_qi_per_hour": round(max(float(mining_qi_per_hour), 0.0), 12),
        },
        "recommended_energy_anchor": {
            "reference_mining_qi_per_hour": round(max(float(mining_qi_per_hour), 0.0), 12),
            "reference_power_watts": round(watts, 8),
            "reference_joules_per_token": {model: measured_joules_per_token},
            "implied_qi_per_joule": parity.qi_per_joule,
        },
        "configured": {
            "reference_joules_per_token": configured_joules_per_token,
            "reference_mining_qi_per_hour": configured_mining_rate,
            "reference_power_watts": configured_watts,
        },
        "drift_ratios": {key: round(value, 6) for key, value in drift.items()},
        "drift_warnings": warnings,
    }


def calibrate_from_hardware_validation(
    validation: dict[str, Any],
    *,
    mining_qi_per_hour: float,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Calibrate from a ``hardware_validation.py`` result dict."""
    duration = max(float(validation.get("runtime_duration_seconds", 0.0)), 0.000001)
    watts = float(validation.get("estimated_energy_joules", 0.0)) / duration
    return calibrate_from_measurements(
        tokens_per_second=float(validation.get("tokens_per_second", 0.0)),
        power_watts=watts,
        mining_qi_per_hour=mining_qi_per_hour,
        config=config,
        model=str(validation.get("model_name", "default")),
        gpu_model=str(validation.get("gpu_model", "unknown-gpu")),
        measurement_source="hardware_validation",
    )


def calibration_evidence_record(calibration: dict[str, Any], *, confidence: float, path: str | None = None) -> dict[str, Any]:
    """Append a calibration to the evidence registry.

    Hardware measurements are the missing evidence behind the energy-pricing
    assumptions in ``ECONOMIC_ASSUMPTIONS.md``; recording them here lets the
    assumption tracker and validation dashboard pick them up.
    """
    measurement = calibration["measurement"]
    result = {
        "outcome": "measured",
        "gpu_model": measurement["gpu_model"],
        "model": measurement["model"],
        "measured_joules_per_token": measurement["measured_joules_per_token"],
        "tokens_per_second": measurement["tokens_per_second"],
        "power_watts": measurement["power_watts"],
        "mining_qi_per_hour": measurement["mining_qi_per_hour"],
        "drift_warnings": calibration["drift_warnings"],
    }
    kwargs: dict[str, Any] = {
        "source": f"calibrate.py:{measurement['source']}",
        "category": "energy_benchmark_measurement",
        "result": result,
        "confidence": confidence,
    }
    if path is not None:
        kwargs["path"] = path
    return record_evidence(**kwargs).to_dict()


def _drift_ratio(configured: float, measured: float) -> float:
    if configured <= 0:
        return 0.0 if measured <= 0 else 1.0
    return abs(measured - configured) / configured


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Calibrate energy_anchor config values from hardware measurements"
    )
    parser.add_argument("--config", default="config.marketplace.yaml")
    parser.add_argument("--mining-qi-per-hour", type=float, default=0.05)
    parser.add_argument("--tokens-per-second", type=float, default=None, help="Skip the validation run and use this measurement")
    parser.add_argument("--power-watts", type=float, default=None, help="Required with --tokens-per-second")
    parser.add_argument("--model", default="llama-3.1-8b")
    parser.add_argument("--gpu-model", default="unknown-gpu")
    parser.add_argument("--runtime-type", default="simulated", choices=("simulated", "subprocess"))
    parser.add_argument("--power-estimate-watts", type=float, default=250.0)
    parser.add_argument("--requests", type=int, default=3)
    parser.add_argument("--record-evidence", action="store_true", help="Append the measurement to evidence_registry.jsonl")
    parser.add_argument("--confidence", type=float, default=0.5)
    args = parser.parse_args()
    config = load_config(args.config)
    if args.tokens_per_second is not None and args.power_watts is not None:
        calibration = calibrate_from_measurements(
            tokens_per_second=args.tokens_per_second,
            power_watts=args.power_watts,
            mining_qi_per_hour=args.mining_qi_per_hour,
            config=config,
            model=args.model,
            gpu_model=args.gpu_model,
        )
    else:
        validation = run_hardware_validation(
            gpu_model=args.gpu_model,
            runtime_type=args.runtime_type,
            model_name=args.model,
            power_estimate_watts=args.power_estimate_watts,
            requests=args.requests,
        )
        calibration = calibrate_from_hardware_validation(
            validation.to_dict(),
            mining_qi_per_hour=args.mining_qi_per_hour,
            config=config,
        )
    if args.record_evidence:
        calibration["evidence_record"] = calibration_evidence_record(calibration, confidence=args.confidence)
    print(json.dumps(calibration, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
