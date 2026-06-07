from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from typing import Any

from runtime import SimulatedRuntime, SubprocessRuntime


@dataclass(frozen=True)
class HardwareValidationResult:
    gpu_model: str
    runtime_type: str
    model_name: str
    tokens_per_second: float
    requests_per_second: float
    utilization: float
    runtime_duration_seconds: float
    estimated_energy_joules: float
    output_hashes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "gpu_model": self.gpu_model,
            "runtime_type": self.runtime_type,
            "model_name": self.model_name,
            "tokens_per_second": self.tokens_per_second,
            "requests_per_second": self.requests_per_second,
            "utilization": self.utilization,
            "runtime_duration_seconds": self.runtime_duration_seconds,
            "estimated_energy_joules": self.estimated_energy_joules,
            "output_hashes": list(self.output_hashes),
        }


def run_hardware_validation(
    *,
    gpu_model: str = "unknown-gpu",
    runtime_type: str = "simulated",
    model_name: str = "validation-model",
    power_estimate_watts: float = 100.0,
    test_duration_seconds: float = 1.0,
    requests: int = 3,
) -> HardwareValidationResult:
    runtime = _runtime(runtime_type)
    request_count = max(int(requests), 1)
    config = _config(runtime_type, power_estimate_watts)
    output_hashes: list[str] = []
    total_tokens = 0.0
    started = time.perf_counter()
    for index in range(request_count):
        result = runtime.run(_job(index, model_name), config)
        output_hashes.append(result.output_hash)
        total_tokens += result.output_tokens
    duration = max(time.perf_counter() - started, 0.000001)
    target_duration = max(float(test_duration_seconds), duration)
    utilization = min(duration / target_duration, 1.0)
    return HardwareValidationResult(
        gpu_model=str(gpu_model),
        runtime_type=runtime_type,
        model_name=str(model_name),
        tokens_per_second=round(total_tokens / duration, 12),
        requests_per_second=round(request_count / duration, 12),
        utilization=round(utilization, 12),
        runtime_duration_seconds=round(duration, 12),
        estimated_energy_joules=round(max(float(power_estimate_watts), 0.0) * duration, 12),
        output_hashes=output_hashes,
    )


def _runtime(runtime_type: str) -> Any:
    if runtime_type == "subprocess":
        return SubprocessRuntime()
    return SimulatedRuntime()


def _config(runtime_type: str, power_estimate_watts: float) -> dict[str, Any]:
    return {
        "worker": {"id": "hardware-validation-worker", "fallback_watts": max(float(power_estimate_watts), 0.0)},
        "runtime": {
            "type": runtime_type,
            "simulated_seconds": 0.001,
            "command": [sys.executable, "-c", "print('validation output')"],
            "timeout_seconds": 5,
        },
        "privacy": {"zero_retention_runtime": True},
    }


def _job(index: int, model_name: str) -> dict[str, Any]:
    return {
        "job_id": f"hardware-validation-{index}",
        "worker_id": "hardware-validation-worker",
        "model": model_name,
        "input_tokens": 8,
        "expected_output_tokens": 32,
        "seconds": 0.001,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect local hardware validation measurements without storing raw outputs")
    parser.add_argument("--gpu-model", default="unknown-gpu")
    parser.add_argument("--runtime-type", default="simulated", choices=("simulated", "subprocess"))
    parser.add_argument("--model-name", default="validation-model")
    parser.add_argument("--power-estimate-watts", type=float, default=100.0)
    parser.add_argument("--test-duration-seconds", type=float, default=1.0)
    parser.add_argument("--requests", type=int, default=3)
    args = parser.parse_args()
    result = run_hardware_validation(
        gpu_model=args.gpu_model,
        runtime_type=args.runtime_type,
        model_name=args.model_name,
        power_estimate_watts=args.power_estimate_watts,
        test_duration_seconds=args.test_duration_seconds,
        requests=args.requests,
    )
    print(result.to_dict())


if __name__ == "__main__":
    main()
