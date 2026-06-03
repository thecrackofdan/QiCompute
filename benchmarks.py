from __future__ import annotations

import argparse
import sys
import time
from statistics import mean
from typing import Any

from runtime import SimulatedRuntime, SubprocessRuntime


def run_benchmarks(iterations: int = 3) -> dict[str, Any]:
    return {
        "simulated": _benchmark_runtime(SimulatedRuntime(), iterations, _base_config("simulated")),
        "subprocess": _benchmark_runtime(SubprocessRuntime(), iterations, _base_config("subprocess")),
    }


def print_benchmarks(results: dict[str, Any]) -> None:
    for name, result in results.items():
        print(
            f"{name}: jobs/sec={result['jobs_per_second']:.3f} "
            f"tokens/sec={result['tokens_per_second']:.3f} "
            f"avg_latency_ms={result['average_latency_ms']:.3f} "
            f"avg_energy_joules={result['average_energy_joules']:.6f}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run lightweight QiCompute runtime benchmark stubs")
    parser.add_argument("--iterations", type=int, default=3)
    args = parser.parse_args()
    print_benchmarks(run_benchmarks(max(args.iterations, 1)))
    return 0


def _benchmark_runtime(runtime: Any, iterations: int, config: dict[str, Any]) -> dict[str, float]:
    durations: list[float] = []
    tokens: list[float] = []
    energy: list[float] = []
    started = time.monotonic()
    for index in range(iterations):
        result = runtime.run(_job(index), config)
        durations.append(result.duration_seconds)
        tokens.append(result.output_tokens)
        energy.append(float(result.metadata.get("energy_joules", 0)))
    elapsed = max(time.monotonic() - started, 0.000001)
    total_tokens = sum(tokens)
    return {
        "jobs_per_second": iterations / elapsed,
        "tokens_per_second": total_tokens / elapsed,
        "average_latency_ms": mean(durations) * 1000,
        "average_energy_joules": mean(energy),
    }


def _base_config(runtime_type: str) -> dict[str, Any]:
    command = [sys.executable, "-c", "print('benchmark output')"]
    return {
        "worker": {"id": "benchmark-worker", "fallback_watts": 100},
        "runtime": {"type": runtime_type, "command": command, "timeout_seconds": 5, "simulated_seconds": 0},
    }


def _job(index: int) -> dict[str, Any]:
    return {
        "job_id": f"benchmark-job-{index}",
        "worker_id": "benchmark-worker",
        "model": "benchmark-model",
        "input_tokens": 4,
        "expected_output_tokens": 16,
    }


if __name__ == "__main__":
    raise SystemExit(main())
