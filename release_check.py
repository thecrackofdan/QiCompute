from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from determinism import run_determinism_checks
from license_check import run_license_checks
from reliability_report import generate_reliability_report
from run_tests import validate_categories
from version import current_version


@dataclass(frozen=True)
class ReleaseCheck:
    name: str
    status: str
    details: str


REQUIRED_FILES = (
    "VERSION",
    "CHANGELOG.md",
    "RELEASE_NOTES_0.1.0.md",
    "MVP.md",
    "SECURITY.md",
    "PROJECT_INFO.md",
    "SHOWCASE.md",
    "README.md",
    "ARCHITECTURE.md",
    "ROADMAP.md",
    "DEVELOPMENT.md",
    "agents.py",
    "agent_simulation.py",
    "economic_scheduler.py",
    "market_demand.py",
    "mining_economics.py",
    "reinvestment.py",
    "economy_simulation.py",
    "crossover.py",
    "economy_report.py",
    "customer_demand.py",
    "market_pricing.py",
    "federation_simulation.py",
    "agent_competition.py",
    "reputation_dynamics.py",
    "regional_market.py",
    "agent_to_agent.py",
    "monetary_simulation.py",
    "economy_dashboard.py",
    "THESIS.md",
    ".github/workflows/smoke.yml",
    ".github/workflows/full_validation.yml",
    "fixtures/epoch_summary.json",
    "fixtures/invoice_summary.json",
    "fixtures/cluster_snapshot.json",
    "fixtures/settlement_example.json",
    "fixtures/load_test_sample.json",
)


def run_release_checks(dynamic: bool = True) -> list[ReleaseCheck]:
    checks = [_file_check(path) for path in REQUIRED_FILES]
    checks.append(_version_check())
    checks.append(_test_category_check())
    checks.extend(_license_checks())
    if dynamic:
        checks.append(_determinism_check())
        checks.append(_reliability_check())
    return checks


def _file_check(path: str) -> ReleaseCheck:
    exists = Path(path).exists()
    return ReleaseCheck(path, "PASS" if exists else "FAIL", "present" if exists else "missing")


def _version_check() -> ReleaseCheck:
    try:
        version = current_version()
    except FileNotFoundError:
        return ReleaseCheck("version", "FAIL", "VERSION missing")
    return ReleaseCheck("version", "PASS" if version == "0.1.0" else "WARN", version)


def _test_category_check() -> ReleaseCheck:
    missing = validate_categories()
    return ReleaseCheck("test categories", "PASS" if not missing else "FAIL", f"uncategorized={len(missing)}")


def _license_checks() -> list[ReleaseCheck]:
    return [ReleaseCheck(f"license: {check.name}", check.status, check.details) for check in run_license_checks()]


def _determinism_check() -> ReleaseCheck:
    result = run_determinism_checks()
    return ReleaseCheck("determinism", "PASS" if result["accepted"] else "FAIL", "deterministic checks accepted")


def _reliability_check() -> ReleaseCheck:
    report = generate_reliability_report()
    return ReleaseCheck("reliability", report["status"], f"settlement={report['settlement_reconciliation']}")


def main() -> int:
    checks = run_release_checks(dynamic=True)
    for check in checks:
        print(f"{check.status} {check.name}: {check.details}")
    return 0 if all(check.status != "FAIL" for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
