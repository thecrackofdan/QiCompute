from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from cluster_demo import run_cluster_demo


def run_lan_smoke_test(db_path: str | None = None) -> dict[str, Any]:
    path = db_path or "/tmp/qicompute-lan-smoke.db"
    result = run_cluster_demo(db_path=path, reset_db=True, worker_count=2, job_count=3, simulate_worker_failure=True)
    return {
        "accepted": result["metrics"]["jobs_completed"] >= 1,
        "jobs_completed": result["metrics"]["jobs_completed"],
        "reassigned_jobs": result["metrics"]["reassigned_jobs"],
        "total_settled_qi": result["metrics"]["total_settled_qi"],
        "epoch_id": result["epoch"]["epoch_id"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a local deterministic QiCompute LAN smoke test")
    parser.add_argument("--db-path")
    args = parser.parse_args()
    result = run_lan_smoke_test(args.db_path)
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
