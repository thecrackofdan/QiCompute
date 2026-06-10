from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import failures
from accounts import customer_balance, refund_job_escrow
from db import WorkerDB
from receipts import utc_now_iso
from treasury import record_refund


def record_rate_limit_event(db: WorkerDB, actor_type: str, actor_id: str, event_type: str, metadata: dict[str, Any] | None = None) -> None:
    db.record_rate_limit_event(
        {
            "event_id": str(uuid4()),
            "actor_type": actor_type,
            "actor_id": actor_id,
            "event_type": event_type,
            "created_at": utc_now_iso(),
            "metadata": metadata or {},
        }
    )


def rate_limit_allowed(
    db: WorkerDB,
    *,
    actor_type: str,
    actor_id: str,
    event_type: str,
    limit: int,
    window_seconds: int = 60,
    now: datetime | None = None,
) -> bool:
    base = now or datetime.now(timezone.utc)
    since = (base - timedelta(seconds=window_seconds)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return db.rate_limit_count(actor_type, actor_id, event_type, since) < int(limit)


def validate_job_escrow_request(db: WorkerDB, customer_id: str, amount_qi: float, config: dict[str, Any]) -> dict[str, Any]:
    marketplace = config.get("marketplace", {})
    minimum = float(marketplace.get("min_job_escrow_qi", 0))
    maximum = float(marketplace.get("max_outstanding_escrow_qi", 1_000_000_000))
    if amount_qi < minimum:
        return {"accepted": False, "failure_code": failures.ESCROW_UNDERFUNDED, "reason": "job escrow below configured minimum"}
    outstanding = customer_balance(db, customer_id)["escrowed_qi"]
    if outstanding + amount_qi > maximum:
        return {"accepted": False, "failure_code": failures.ESCROW_LIMIT_EXCEEDED, "reason": "customer escrow limit exceeded"}
    return {"accepted": True, "failure_code": None, "reason": "escrow accepted"}


def expire_escrows(db: WorkerDB, now: str | None = None, expiry_seconds: int = 600) -> int:
    from datetime import datetime

    current = now or utc_now_iso()
    rows = db.conn.execute(
        """
        SELECT *
        FROM job_escrows
        WHERE status = 'escrowed'
        """
    ).fetchall()
    expired = 0
    for row in rows:
        created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
        current_dt = datetime.fromisoformat(current.replace("Z", "+00:00"))
        if (current_dt - created).total_seconds() >= expiry_seconds:
            refund = refund_job_escrow(db, row["job_id"], failures.ESCROW_EXPIRED)
            record_refund(db, refund_qi=refund.get("refund_qi", 0))
            expired += 1
    return expired
