from __future__ import annotations

from typing import Any

from db import WorkerDB
from receipts import utc_now_iso


DEFAULT_TREASURY_ID = "local-marketplace"


def get_treasury(db: WorkerDB, treasury_id: str = DEFAULT_TREASURY_ID) -> dict[str, Any]:
    _ensure_treasury(db, treasury_id)
    row = db.conn.execute("SELECT * FROM marketplace_treasury WHERE treasury_id = ?", (treasury_id,)).fetchone()
    return {
        "treasury_id": row["treasury_id"],
        "total_fees_collected": float(row["total_fees_collected"]),
        "total_worker_payouts": float(row["total_worker_payouts"]),
        "total_customer_refunds": float(row["total_customer_refunds"]),
        "total_disputed_volume": float(row["total_disputed_volume"]),
        "total_settled_volume": float(row["total_settled_volume"]),
        "updated_at": row["updated_at"],
    }


def record_settlement(
    db: WorkerDB,
    *,
    fee_qi: float,
    worker_payout_qi: float,
    settled_qi: float,
    treasury_id: str = DEFAULT_TREASURY_ID,
) -> dict[str, Any]:
    now = utc_now_iso()
    with db.conn:
        _ensure_treasury(db, treasury_id)
        db.conn.execute(
            """
            UPDATE marketplace_treasury
            SET total_fees_collected = total_fees_collected + ?,
                total_worker_payouts = total_worker_payouts + ?,
                total_settled_volume = total_settled_volume + ?,
                updated_at = ?
            WHERE treasury_id = ?
            """,
            (float(fee_qi), float(worker_payout_qi), float(settled_qi), now, treasury_id),
        )
    return get_treasury(db, treasury_id)


def record_refund(db: WorkerDB, *, refund_qi: float, disputed: bool = False, treasury_id: str = DEFAULT_TREASURY_ID) -> dict[str, Any]:
    now = utc_now_iso()
    with db.conn:
        _ensure_treasury(db, treasury_id)
        db.conn.execute(
            """
            UPDATE marketplace_treasury
            SET total_customer_refunds = total_customer_refunds + ?,
                total_disputed_volume = total_disputed_volume + ?,
                updated_at = ?
            WHERE treasury_id = ?
            """,
            (float(refund_qi), float(refund_qi) if disputed else 0.0, now, treasury_id),
        )
    return get_treasury(db, treasury_id)


def _ensure_treasury(db: WorkerDB, treasury_id: str) -> None:
    db.conn.execute(
        """
        INSERT INTO marketplace_treasury (
            treasury_id, total_fees_collected, total_worker_payouts,
            total_customer_refunds, total_disputed_volume,
            total_settled_volume, updated_at
        ) VALUES (?, 0, 0, 0, 0, 0, ?)
        ON CONFLICT(treasury_id) DO NOTHING
        """,
        (treasury_id, utc_now_iso()),
    )
