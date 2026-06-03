from __future__ import annotations

import argparse
from typing import Any

from load_test import run_load_test


def generate_bottleneck_report(workers: int = 25, jobs: int = 500, mode: str = "honest", seed: int = 42) -> dict[str, Any]:
    result = run_load_test(workers=workers, jobs=jobs, mode=mode, seed=seed)
    stage_metrics = result["stage_metrics"]
    return {
        "routing_time": stage_metrics.get("routing", {}).get("total", 0.0),
        "db_write_time": stage_metrics.get("db_write", {}).get("total", 0.0),
        "verification_time": stage_metrics.get("verification", {}).get("total", 0.0),
        "committee_time": stage_metrics.get("committee", {}).get("total", 0.0),
        "settlement_time": stage_metrics.get("settlement", {}).get("total", 0.0),
        "execution_time": stage_metrics.get("execution", {}).get("total", 0.0),
        "total_runtime": sum(summary.get("total", 0.0) for summary in stage_metrics.values()),
        "slowest_stage": result["bottleneck"]["slowest_stage"],
        "recommended_next_optimization": result["bottleneck"]["recommendation"],
        "jobs_completed": result["jobs_completed"],
        "throughput_jobs_sec": result["throughput_jobs_sec"],
    }


def print_bottleneck_report(report: dict[str, Any]) -> None:
    print("QiCompute Bottleneck Report")
    for key, value in report.items():
        print(f"{key}: {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a QiCompute bottleneck report")
    parser.add_argument("--workers", type=int, default=25)
    parser.add_argument("--jobs", type=int, default=500)
    parser.add_argument("--mode", choices=("honest", "flaky", "malicious", "mixed"), default="honest")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    print_bottleneck_report(generate_bottleneck_report(max(1, args.workers), max(0, args.jobs), args.mode, args.seed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
