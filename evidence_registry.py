from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from receipts import utc_now_iso


DEFAULT_EVIDENCE_PATH = Path("evidence_registry.jsonl")


@dataclass(frozen=True)
class EvidenceRecord:
    timestamp: str
    source: str
    category: str
    result: dict[str, Any]
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "source": self.source,
            "category": self.category,
            "result": self.result,
            "confidence": self.confidence,
        }


def record_evidence(
    *,
    source: str,
    category: str,
    result: dict[str, Any],
    confidence: float,
    path: str | Path = DEFAULT_EVIDENCE_PATH,
) -> EvidenceRecord:
    record = EvidenceRecord(
        timestamp=utc_now_iso(),
        source=str(source),
        category=str(category),
        result=result,
        confidence=round(min(max(float(confidence), 0.0), 1.0), 6),
    )
    evidence_path = Path(path)
    with evidence_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
    return record


def list_evidence(path: str | Path = DEFAULT_EVIDENCE_PATH) -> list[EvidenceRecord]:
    evidence_path = Path(path)
    if not evidence_path.exists():
        return []
    records = []
    for line in evidence_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        records.append(
            EvidenceRecord(
                timestamp=payload["timestamp"],
                source=payload["source"],
                category=payload["category"],
                result=dict(payload.get("result", {})),
                confidence=float(payload.get("confidence", 0.0)),
            )
        )
    return records


def summarize_evidence(path: str | Path = DEFAULT_EVIDENCE_PATH) -> dict[str, Any]:
    records = list_evidence(path)
    by_category: dict[str, dict[str, float]] = {}
    for record in records:
        summary = by_category.setdefault(record.category, {"count": 0, "confidence_total": 0.0})
        summary["count"] += 1
        summary["confidence_total"] += record.confidence
    return {
        "total_records": len(records),
        "categories": {
            category: {
                "count": int(values["count"]),
                "average_confidence": round(values["confidence_total"] / max(values["count"], 1), 6),
            }
            for category, values in sorted(by_category.items())
        },
    }
