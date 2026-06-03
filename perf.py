from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = max(0.0, min(100.0, float(pct))) / 100.0 * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


@dataclass
class MetricsAccumulator:
    values: dict[str, list[float]] = field(default_factory=dict)

    def add(self, name: str, value: float) -> None:
        self.values.setdefault(name, []).append(float(value))

    def count(self, name: str) -> int:
        return len(self.values.get(name, []))

    def summary(self, name: str) -> dict[str, float]:
        values = self.values.get(name, [])
        total = sum(values)
        return {
            "count": float(len(values)),
            "total": total,
            "average": total / len(values) if values else 0.0,
            "p50": percentile(values, 50),
            "p95": percentile(values, 95),
            "p99": percentile(values, 99),
        }

    def summaries(self) -> dict[str, dict[str, float]]:
        return {name: self.summary(name) for name in sorted(self.values)}


@contextmanager
def timer(metrics: MetricsAccumulator, name: str) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    finally:
        metrics.add(name, time.perf_counter() - started)


def timed_query(metrics: MetricsAccumulator, name: str, conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    with timer(metrics, name):
        return list(conn.execute(sql, params))


def bottleneck_summary(stage_totals: dict[str, float]) -> dict[str, Any]:
    if not stage_totals:
        return {"slowest_stage": None, "recommendation": "No measured stages."}
    slowest = max(stage_totals.items(), key=lambda item: item[1])
    recommendations = {
        "routing": "Add routing indexes and cache eligible workers by model.",
        "db_write": "Batch writes or move hot paths to fewer transactions.",
        "verification": "Cache deterministic verification inputs and defer noncritical checks.",
        "committee": "Reduce committee size for low-risk QoS or batch vote writes.",
        "settlement": "Batch epoch settlement writes and summarize with aggregate queries.",
        "execution": "Increase worker slots or improve model warm-cache locality.",
    }
    return {
        "slowest_stage": slowest[0],
        "slowest_seconds": slowest[1],
        "recommendation": recommendations.get(slowest[0], "Inspect the measured stage with the highest cumulative time."),
    }
