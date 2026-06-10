from __future__ import annotations

from typing import Any


WORKER_CLASSES = ("honest", "flaky", "malicious", "falsely_accused", "recovering")


def run_reputation_dynamics(cycles: int = 100) -> dict[str, Any]:
    reputations = {worker_class: 0.65 for worker_class in WORKER_CLASSES}
    penalties = {worker_class: 0 for worker_class in WORKER_CLASSES}
    recovery_cycle: int | None = None
    for cycle in range(max(int(cycles), 0)):
        for worker_class in WORKER_CLASSES:
            delta, penalized = _class_delta(worker_class, cycle)
            reputations[worker_class] = min(max(reputations[worker_class] + delta, 0.0), 1.0)
            penalties[worker_class] += 1 if penalized else 0
        if recovery_cycle is None and reputations["recovering"] >= 0.75 and cycle > 0:
            recovery_cycle = cycle
    false_positive_penalty_rate = penalties["falsely_accused"] / max(cycles, 1)
    malicious_survives = 1.0 if reputations["malicious"] >= 0.5 else 0.0
    return {
        "cycles": cycles,
        "average_reputation_by_class": {key: round(value, 12) for key, value in reputations.items()},
        "false_positive_penalty_rate": round(false_positive_penalty_rate, 12),
        "malicious_worker_survival_rate": malicious_survives,
        "recovery_time": recovery_cycle if recovery_cycle is not None else cycles,
    }


def _class_delta(worker_class: str, cycle: int) -> tuple[float, bool]:
    if worker_class == "honest":
        return (0.006, False)
    if worker_class == "flaky":
        return (-0.025, True) if cycle % 5 == 0 else (0.003, False)
    if worker_class == "malicious":
        return (-0.08, True) if cycle % 3 == 0 else (-0.01, False)
    if worker_class == "falsely_accused":
        return (-0.035, True) if cycle in {8, 31} else (0.005, False)
    if worker_class == "recovering":
        return (-0.04, True) if cycle < 8 and cycle % 2 == 0 else (0.008, False)
    return (0.0, False)
