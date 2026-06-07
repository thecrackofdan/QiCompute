from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ControllerState:
    name: str
    region: str
    trust_score: float
    capacity: int


def run_federation_simulation(cycles: int = 100) -> dict[str, Any]:
    controllers = (
        ControllerState("controller_a", "Atlantic Canada", 0.98, 4),
        ControllerState("controller_b", "US East", 0.94, 6),
        ControllerState("controller_c", "Europe", 0.90, 5),
    )
    metrics = {
        "controllers": len(controllers),
        "jobs_routed_locally": 0,
        "jobs_handed_off": 0,
        "failed_handoffs": 0,
        "verifier_handoffs": 0,
        "settlement_mismatches": 0,
        "trust_boundaries_checked": 0,
    }
    for cycle in range(max(int(cycles), 0)):
        controller = controllers[cycle % len(controllers)]
        demand = 2 + (cycle % 7)
        if demand <= controller.capacity:
            metrics["jobs_routed_locally"] += demand
        else:
            local = controller.capacity
            handoff = demand - local
            metrics["jobs_routed_locally"] += local
            metrics["jobs_handed_off"] += handoff
            metrics["trust_boundaries_checked"] += handoff
            if controller.trust_score < 0.92 and cycle % 5 == 0:
                metrics["failed_handoffs"] += 1
        if cycle % 4 == 0:
            metrics["verifier_handoffs"] += 1
        if cycle % 37 == 0 and cycle != 0:
            metrics["settlement_mismatches"] += 1
    reconciled = max(metrics["jobs_handed_off"] - metrics["settlement_mismatches"], 0)
    metrics["reconciliation_success_rate"] = round(reconciled / max(metrics["jobs_handed_off"], 1), 12)
    return metrics
