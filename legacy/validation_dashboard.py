from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from assumption_tracker import summarize_assumptions
from evidence_registry import summarize_evidence


def build_validation_dashboard(
    *,
    assumptions_path: str | Path = "ECONOMIC_ASSUMPTIONS.md",
    evidence_path: str | Path = "evidence_registry.jsonl",
) -> dict[str, Any]:
    assumptions = summarize_assumptions(assumptions_path=assumptions_path, evidence_path=evidence_path)
    evidence = summarize_evidence(evidence_path)
    counts = assumptions["status_counts"]
    return {
        "assumptions_validated": _indicator(counts["validated"] > 0, counts["untested"] == assumptions["total_assumptions"]),
        "assumptions_contradicted": _indicator(counts["contradicted"] == 0, counts["untested"] == assumptions["total_assumptions"]),
        "benchmark_summaries": _category_indicator(evidence, "benchmark"),
        "mining_inference_crossover": _category_indicator(evidence, "crossover"),
        "verification_overhead": _category_indicator(evidence, "verification"),
        "customer_feedback_summary": _category_indicator(evidence, "customer"),
        "evidence_summary": evidence,
        "assumption_summary": assumptions,
    }


def _category_indicator(evidence: dict[str, Any], prefix: str) -> str:
    categories = evidence.get("categories", {})
    matched = [values for category, values in categories.items() if prefix in category]
    if not matched:
        return "UNKNOWN"
    avg = sum(item["average_confidence"] for item in matched) / len(matched)
    return "PASS" if avg >= 0.7 else "WARN"


def _indicator(good: bool, unknown: bool) -> str:
    if unknown:
        return "UNKNOWN"
    return "PASS" if good else "WARN"


def main() -> None:
    parser = argparse.ArgumentParser(description="Report QiCompute validation evidence without hype")
    parser.add_argument("--evidence-path", default="evidence_registry.jsonl")
    args = parser.parse_args()
    dashboard = build_validation_dashboard(evidence_path=args.evidence_path)
    for key, value in dashboard.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
