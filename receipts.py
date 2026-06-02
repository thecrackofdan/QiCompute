from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class JobReceipt:
    worker_id: str
    mode: str
    started_at: str
    ended_at: str
    duration_seconds: float
    average_watts: float
    output_type: str
    output_amount: float
    estimated_qi_owed: float
    metadata: dict[str, Any] = field(default_factory=dict)
    receipt_id: str = field(default_factory=lambda: str(uuid4()))

    @property
    def energy_joules(self) -> float:
        return self.average_watts * self.duration_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "worker_id": self.worker_id,
            "mode": self.mode,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_seconds": self.duration_seconds,
            "average_watts": self.average_watts,
            "energy_joules": self.energy_joules,
            "output": {
                "type": self.output_type,
                "amount": self.output_amount,
            },
            "estimated_qi_owed": self.estimated_qi_owed,
            "metadata": self.metadata,
        }


def make_receipt(
    *,
    worker_id: str,
    mode: str,
    started_at: str,
    ended_at: str,
    duration_seconds: float,
    average_watts: float,
    output_type: str,
    output_amount: float,
    estimated_qi_owed: float,
    metadata: dict[str, Any] | None = None,
) -> JobReceipt:
    return JobReceipt(
        worker_id=worker_id,
        mode=mode,
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=round(duration_seconds, 3),
        average_watts=round(average_watts, 3),
        output_type=output_type,
        output_amount=round(output_amount, 8),
        estimated_qi_owed=round(estimated_qi_owed, 12),
        metadata=metadata or {},
    )
