from __future__ import annotations

import argparse
import sys
import unittest


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


def select_suite(category: str) -> unittest.TestSuite:
    suite = unittest.defaultTestLoader.discover(".")
    if category == "all":
        return suite
    selected = unittest.TestSuite()
    for case in _iter_cases(suite):
        test_id = case.id().lower()
        if _matches_category(test_id, category):
            selected.addTest(case)
    return selected


def _matches_category(test_id: str, category: str) -> bool:
    if category == "simulation":
        return any(keyword in test_id for keyword in SIMULATION_KEYWORDS)
    if category == "integration":
        return any(keyword in test_id for keyword in INTEGRATION_KEYWORDS)
    if category == "slow":
        return any(keyword in test_id for keyword in SLOW_KEYWORDS)
    if category == "unit":
        return not any(keyword in test_id for keyword in INTEGRATION_KEYWORDS + SIMULATION_KEYWORDS + SLOW_KEYWORDS)
    return True


def _iter_cases(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _iter_cases(item)
        else:
            yield item


def main() -> int:
    parser = argparse.ArgumentParser(description="Run QiCompute tests by category")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--unit", action="store_true")
    group.add_argument("--integration", action="store_true")
    group.add_argument("--simulation", action="store_true")
    group.add_argument("--slow", action="store_true")
    group.add_argument("--all", action="store_true")
    args = parser.parse_args()
    category = "all"
    for candidate in ("unit", "integration", "simulation", "slow", "all"):
        if getattr(args, candidate):
            category = candidate
            break
    result = unittest.TextTestRunner(verbosity=2).run(select_suite(category))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
