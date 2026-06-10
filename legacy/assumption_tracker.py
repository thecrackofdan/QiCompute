from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evidence_registry import EvidenceRecord, list_evidence


STATUSES = ("untested", "partially validated", "validated", "contradicted")


@dataclass(frozen=True)
class AssumptionStatus:
    assumption: str
    status: str
    evidence_count: int
    average_confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "assumption": self.assumption,
            "status": self.status,
            "evidence_count": self.evidence_count,
            "average_confidence": self.average_confidence,
        }


def load_assumptions(path: str | Path = "ECONOMIC_ASSUMPTIONS.md") -> list[str]:
    text = Path(path).read_text(encoding="utf-8")
    assumptions = []
    for line in text.splitlines():
        if not line.startswith("| "):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells or cells[0] in {"Assumption", "---"}:
            continue
        assumptions.append(cells[0])
    return assumptions


def track_assumptions(
    *,
    assumptions_path: str | Path = "ECONOMIC_ASSUMPTIONS.md",
    evidence_path: str | Path = "evidence_registry.jsonl",
) -> list[AssumptionStatus]:
    assumptions = load_assumptions(assumptions_path)
    evidence = list_evidence(evidence_path)
    return [_status_for_assumption(assumption, evidence) for assumption in assumptions]


def summarize_assumptions(
    *,
    assumptions_path: str | Path = "ECONOMIC_ASSUMPTIONS.md",
    evidence_path: str | Path = "evidence_registry.jsonl",
) -> dict[str, Any]:
    statuses = track_assumptions(assumptions_path=assumptions_path, evidence_path=evidence_path)
    counts = {status: 0 for status in STATUSES}
    for item in statuses:
        counts[item.status] += 1
    return {
        "total_assumptions": len(statuses),
        "status_counts": counts,
        "assumptions": [item.to_dict() for item in statuses],
    }


def _status_for_assumption(assumption: str, evidence: list[EvidenceRecord]) -> AssumptionStatus:
    linked = [record for record in evidence if _matches(assumption, record)]
    if not linked:
        return AssumptionStatus(assumption, "untested", 0, 0.0)
    negative = [record for record in linked if str(record.result.get("outcome", "")).lower() in {"contradicted", "negative", "failed"}]
    average = sum(record.confidence for record in linked) / len(linked)
    if negative and sum(record.confidence for record in negative) / len(negative) >= 0.6:
        status = "contradicted"
    elif average >= 0.75 and len(linked) >= 2:
        status = "validated"
    else:
        status = "partially validated"
    return AssumptionStatus(assumption, status, len(linked), round(average, 6))


def _matches(assumption: str, record: EvidenceRecord) -> bool:
    haystack = f"{record.category} {record.source} {record.result}".lower()
    words = [word.strip(".,:;()").lower() for word in assumption.split() if len(word.strip(".,:;()")) > 4]
    return any(word in haystack for word in words)
