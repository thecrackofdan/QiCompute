from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from accounting_checks import run_accounting_checks
from bottleneck_report import generate_bottleneck_report
from db import WorkerDB
from load_test import run_load_test
from reliability_report import generate_reliability_report
from run_tests import select_suite


def generate_dev_health() -> dict[str, Any]:
    smoke_count = select_suite("smoke").countTestCases()
    full_count = select_suite("all").countTestCases()
    smoke_started = time.perf_counter()
    smoke = subprocess.run([sys.executable, "run_tests.py", "--smoke"], capture_output=True, text=True, check=False)
    smoke_runtime = time.perf_counter() - smoke_started
    load_started = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmp:
        load = run_load_test(workers=2, jobs=4, db_path=str(Path(tmp) / "health-load.db"))
        db = WorkerDB(str(Path(tmp) / "health-checks.db"))
        try:
            accounting = run_accounting_checks(db, mode="quick")
        finally:
            db.close()
    load_runtime = time.perf_counter() - load_started
    bottleneck = generate_bottleneck_report(workers=2, jobs=4)
    reliability = generate_reliability_report()
    warnings = []
    if smoke.returncode != 0:
        warnings.append("smoke tests failed")
    if load["accounting_reconciliation"] != "PASS":
        warnings.append("load test accounting did not reconcile")
    if any(check.status == "FAIL" for check in accounting):
        warnings.append("quick accounting checks failed")
    if reliability["status"] != "PASS":
        warnings.append("reliability report failed")
    return {
        "test_count": full_count,
        "smoke_test_count": smoke_count,
        "smoke_runtime": smoke_runtime,
        "full_runtime": "not measured by dev_health",
        "load_test_runtime": load_runtime,
        "bottleneck_status": bottleneck["slowest_stage"],
        "accounting_status": "PASS" if all(check.status != "FAIL" for check in accounting) else "FAIL",
        "reliability_status": reliability["status"],
        "outstanding_warnings": warnings,
    }


def print_dev_health(report: dict[str, Any]) -> None:
    print("QiCompute Development Health")
    for key, value in report.items():
        print(f"{key}: {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Show local QiCompute development health")
    parser.parse_args()
    report = generate_dev_health()
    print_dev_health(report)
    return 0 if not report["outstanding_warnings"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
