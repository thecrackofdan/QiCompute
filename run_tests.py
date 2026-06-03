from __future__ import annotations

import argparse
import time
import unittest
from dataclasses import dataclass
from typing import Iterable


SIMULATION_KEYWORDS = ("simulation", "stress", "demo", "load", "economic", "cluster_demo")
INTEGRATION_KEYWORDS = (
    "controller",
    "daemon",
    "cluster",
    "lan",
    "ollama",
    "subprocess",
    "runtime",
    "escrow",
    "settlement",
    "enrollment",
    "transport",
)
SLOW_KEYWORDS = ("stress", "simulation", "demo", "cluster_demo", "lan_smoke", "benchmark", "load")
SMOKE_NAMES = {
    "test_worker.WorkerPrototypeTest.test_doctor_runs_successfully",
    "test_worker.WorkerPrototypeTest.test_makefile_commands_exist",
    "test_worker.WorkerPrototypeTest.test_architecture_docs_present",
    "test_worker.WorkerPrototypeTest.test_performance_docs_present",
    "test_worker.WorkerPrototypeTest.test_run_tests_category_selection",
    "test_worker.WorkerPrototypeTest.test_perf_percentile_and_bottleneck_helpers",
    "test_worker.WorkerPrototypeTest.test_database_performance_indexes_exist",
    "test_worker.WorkerPrototypeTest.test_accounting_quick_and_full_modes",
    "test_worker.WorkerPrototypeTest.test_valid_inference_receipt_verification",
    "test_worker.WorkerPrototypeTest.test_receipt_hash_verifies_correctly",
    "test_worker.WorkerPrototypeTest.test_valid_job_envelope_passes",
    "test_worker.WorkerPrototypeTest.test_valid_capability_claim_passes",
    "test_worker.WorkerPrototypeTest.test_strict_privacy_defaults",
}


@dataclass(frozen=True)
class CategorizedTest:
    test_id: str
    categories: set[str]


class ProfilingTextResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._started_at = 0.0
        self.durations: list[tuple[str, float]] = []

    def startTest(self, test):
        self._started_at = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test):
        self.durations.append((test.id(), time.perf_counter() - self._started_at))
        super().stopTest(test)


class ProfilingTextRunner(unittest.TextTestRunner):
    resultclass = ProfilingTextResult


def discover_tests() -> list[unittest.TestCase]:
    return list(_iter_cases(unittest.defaultTestLoader.discover(".")))


def categorize_test(test_id: str) -> set[str]:
    lowered = test_id.lower()
    categories: set[str] = set()
    if test_id in SMOKE_NAMES:
        categories.add("smoke")
    if any(keyword in lowered for keyword in SIMULATION_KEYWORDS):
        categories.add("simulation")
    if any(keyword in lowered for keyword in INTEGRATION_KEYWORDS):
        categories.add("integration")
    if any(keyword in lowered for keyword in SLOW_KEYWORDS):
        categories.add("slow")
    if "smoke" in lowered:
        categories.add("smoke")
    if not categories - {"smoke"}:
        categories.add("unit")
    return categories


def categorized_tests() -> list[CategorizedTest]:
    return [CategorizedTest(test.id(), categorize_test(test.id())) for test in discover_tests()]


def uncategorized_tests() -> list[str]:
    return [item.test_id for item in categorized_tests() if not item.categories]


def select_suite(category: str) -> unittest.TestSuite:
    tests = discover_tests()
    if category == "all":
        return unittest.TestSuite(tests)
    selected = unittest.TestSuite()
    for case in tests:
        if category in categorize_test(case.id()):
            selected.addTest(case)
    return selected


def validate_categories() -> list[str]:
    return uncategorized_tests()


def print_profile(result: ProfilingTextResult, total_runtime: float) -> None:
    durations = sorted(result.durations, key=lambda item: item[1], reverse=True)
    average = sum(duration for _, duration in durations) / len(durations) if durations else 0.0
    suite_totals: dict[str, float] = {}
    for test_id, duration in durations:
        suite_name = test_id.split(".")[0]
        suite_totals[suite_name] = suite_totals.get(suite_name, 0.0) + duration
    print("Test Runtime Profile")
    print(f"total_runtime: {total_runtime:.6f}")
    print(f"average_runtime: {average:.6f}")
    print("slowest_tests:")
    for test_id, duration in durations[:10]:
        print(f"  {duration:.6f} {test_id}")
    print("slowest_suites:")
    for suite_name, duration in sorted(suite_totals.items(), key=lambda item: item[1], reverse=True):
        print(f"  {duration:.6f} {suite_name}")


def _iter_cases(suite: unittest.TestSuite) -> Iterable[unittest.TestCase]:
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _iter_cases(item)
        else:
            yield item


def main() -> int:
    parser = argparse.ArgumentParser(description="Run QiCompute tests by category")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--smoke", action="store_true")
    group.add_argument("--unit", action="store_true")
    group.add_argument("--integration", action="store_true")
    group.add_argument("--simulation", action="store_true")
    group.add_argument("--slow", action="store_true")
    group.add_argument("--all", action="store_true")
    parser.add_argument("--validate-categories", action="store_true")
    parser.add_argument("--profile", action="store_true")
    args = parser.parse_args()
    if args.validate_categories:
        missing = validate_categories()
        if missing:
            print("Uncategorized tests:")
            for test_id in missing:
                print(f"  {test_id}")
            return 1
        print(f"All {len(categorized_tests())} tests have categories.")
        return 0
    category = "all"
    for candidate in ("smoke", "unit", "integration", "simulation", "slow", "all"):
        if getattr(args, candidate):
            category = candidate
            break
    runner_cls = ProfilingTextRunner if args.profile else unittest.TextTestRunner
    runner = runner_cls(verbosity=2)
    started = time.perf_counter()
    result = runner.run(select_suite(category))
    total_runtime = time.perf_counter() - started
    if args.profile and isinstance(result, ProfilingTextResult):
        print_profile(result, total_runtime)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
