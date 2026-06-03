from __future__ import annotations

import argparse
import tempfile
from pathlib import Path
from typing import Any

from accounting_checks import run_accounting_checks
from audit import duplicate_receipts, recent_attacks, suspicious_committees
from db import WorkerDB
from load_test import run_load_test
from run_tests import categorized_tests


def generate_reliability_report() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "reliability.db")
        load = run_load_test(workers=3, jobs=8, mode="mixed", db_path=db_path)
        db = WorkerDB(db_path)
        try:
            checks = run_accounting_checks(db, mode="full")
            attacks = recent_attacks(db)
            duplicate_count = len(duplicate_receipts(db))
            suspicious_count = len(suspicious_committees(db))
        finally:
            db.close()
    categorized = categorized_tests()
    test_counts: dict[str, int] = {}
    for item in categorized:
        for category in item.categories:
            test_counts[category] = test_counts.get(category, 0) + 1
    accounting_pass = all(check.status != "FAIL" for check in checks)
    status = "PASS" if accounting_pass and load["accounting_reconciliation"] == "PASS" and duplicate_count == 0 else "FAIL"
    return {
        "status": status,
        "test_counts": test_counts,
        "pass_rate": 1.0 if status == "PASS" else 0.0,
        "simulation_success_rate": load["jobs_completed"] / max(1, load["jobs_submitted"]),
        "abuse_detection_success_rate": 1.0 if load["attacks_rejected"] >= 1 else 0.0,
        "settlement_reconciliation": load["accounting_reconciliation"],
        "replay_prevention_result": "PASS" if duplicate_count == 0 else "FAIL",
        "committee_dispute_count": load.get("committee_disputes", 0),
        "recent_attack_events": len(attacks),
        "suspicious_committee_count": suspicious_count,
        "warnings": [] if status == "PASS" else ["Reliability checks found a failing signal."],
    }


def print_reliability_report(report: dict[str, Any]) -> None:
    print("QiCompute Reliability Report")
    print(f"status: {report['status']}")
    print(f"test_counts: {report['test_counts']}")
    print(f"pass_rate: {report['pass_rate']}")
    print(f"simulation_success_rate: {report['simulation_success_rate']}")
    print(f"abuse_detection_success_rate: {report['abuse_detection_success_rate']}")
    print(f"settlement_reconciliation: {report['settlement_reconciliation']}")
    print(f"replay_prevention_result: {report['replay_prevention_result']}")
    print(f"committee_dispute_count: {report['committee_dispute_count']}")
    print(f"recent_attack_events: {report['recent_attack_events']}")
    print(f"suspicious_committee_count: {report['suspicious_committee_count']}")
    for warning in report["warnings"]:
        print(f"WARN {warning}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a QiCompute reliability report")
    parser.parse_args()
    report = generate_reliability_report()
    print_reliability_report(report)
    return 0 if report["status"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
