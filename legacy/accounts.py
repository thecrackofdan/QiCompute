from __future__ import annotations

import json
from typing import Any

from db import WorkerDB
from privacy import redact_sensitive_fields
from receipts import utc_now_iso


JOB_SETTLEMENT_STATES = {"pending_funding", "escrowed", "executing", "settled", "refunded", "disputed"}


def create_customer_account(db: WorkerDB, customer_id: str, initial_qi: float = 0.0, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    now = utc_now_iso()
    with db.conn:
        db.conn.execute(
            """
            INSERT INTO customer_accounts (
                customer_id, created_at, available_qi, escrowed_qi,
                spent_qi, refunded_qi, metadata_json
            ) VALUES (?, ?, ?, 0, 0, 0, ?)
            ON CONFLICT(customer_id) DO NOTHING
            """,
            (customer_id, now, float(initial_qi), json.dumps(redact_sensitive_fields(metadata or {}), sort_keys=True)),
        )
    return customer_balance(db, customer_id)


def customer_balance(db: WorkerDB, customer_id: str) -> dict[str, Any]:
    row = db.conn.execute("SELECT * FROM customer_accounts WHERE customer_id = ?", (customer_id,)).fetchone()
    if not row:
        raise ValueError(f"Unknown customer account: {customer_id}")
    return {
        "customer_id": row["customer_id"],
        "created_at": row["created_at"],
        "available_qi": float(row["available_qi"]),
        "escrowed_qi": float(row["escrowed_qi"]),
        "spent_qi": float(row["spent_qi"]),
        "refunded_qi": float(row["refunded_qi"]),
        "metadata": json.loads(row["metadata_json"]),
    }


def escrow_balance(db: WorkerDB, customer_id: str) -> float:
    return customer_balance(db, customer_id)["escrowed_qi"]


def credit_available_balance(db: WorkerDB, customer_id: str, amount_qi: float) -> dict[str, Any]:
    if amount_qi < 0:
        raise ValueError("credit amount cannot be negative")
    create_customer_account(db, customer_id)
    with db.conn:
        db.conn.execute(
            "UPDATE customer_accounts SET available_qi = available_qi + ? WHERE customer_id = ?",
            (float(amount_qi), customer_id),
        )
    return customer_balance(db, customer_id)


def debit_available_balance(db: WorkerDB, customer_id: str, amount_qi: float) -> dict[str, Any]:
    if amount_qi < 0:
        raise ValueError("debit amount cannot be negative")
    account = customer_balance(db, customer_id)
    if account["available_qi"] < amount_qi:
        raise ValueError("insufficient available customer balance")
    with db.conn:
        db.conn.execute(
            "UPDATE customer_accounts SET available_qi = available_qi - ? WHERE customer_id = ?",
            (float(amount_qi), customer_id),
        )
    return customer_balance(db, customer_id)


def escrow_job_funds(db: WorkerDB, job: dict[str, Any], amount_qi: float | None = None) -> dict[str, Any]:
    customer_id = str(job.get("customer_id") or "")
    if not customer_id:
        raise ValueError("job requires customer_id for escrow")
    amount = float(amount_qi if amount_qi is not None else job.get("max_price_qi", 0))
    if amount < 0:
        raise ValueError("escrow amount cannot be negative")
    account = customer_balance(db, customer_id)
    if account["available_qi"] + 1e-12 < amount:
        raise ValueError("insufficient available customer balance")
    now = utc_now_iso()
    with db.conn:
        db.conn.execute(
            """
            UPDATE customer_accounts
            SET available_qi = available_qi - ?,
                escrowed_qi = escrowed_qi + ?
            WHERE customer_id = ?
            """,
            (amount, amount, customer_id),
        )
        db.conn.execute(
            """
            INSERT INTO job_escrows (
                job_id, customer_id, escrowed_qi, settled_qi, fee_qi,
                worker_payout_qi, refunded_qi, status, created_at, updated_at, metadata_json
            ) VALUES (?, ?, ?, 0, 0, 0, 0, 'escrowed', ?, ?, ?)
            ON CONFLICT(job_id) DO NOTHING
            """,
            (
                job["job_id"],
                customer_id,
                amount,
                now,
                now,
                json.dumps(redact_sensitive_fields({"pricing": job.get("metadata", {}).get("price")}), sort_keys=True),
            ),
        )
    return job_escrow(db, job["job_id"])


def release_escrow(db: WorkerDB, customer_id: str, amount_qi: float) -> dict[str, Any]:
    account = customer_balance(db, customer_id)
    if account["escrowed_qi"] + 1e-12 < amount_qi:
        raise ValueError("insufficient escrowed customer balance")
    with db.conn:
        db.conn.execute(
            """
            UPDATE customer_accounts
            SET escrowed_qi = escrowed_qi - ?,
                spent_qi = spent_qi + ?
            WHERE customer_id = ?
            """,
            (float(amount_qi), float(amount_qi), customer_id),
        )
    return customer_balance(db, customer_id)


def refund_escrow(db: WorkerDB, customer_id: str, amount_qi: float) -> dict[str, Any]:
    account = customer_balance(db, customer_id)
    if account["escrowed_qi"] + 1e-12 < amount_qi:
        raise ValueError("insufficient escrowed customer balance")
    with db.conn:
        db.conn.execute(
            """
            UPDATE customer_accounts
            SET escrowed_qi = escrowed_qi - ?,
                available_qi = available_qi + ?,
                refunded_qi = refunded_qi + ?
            WHERE customer_id = ?
            """,
            (float(amount_qi), float(amount_qi), float(amount_qi), customer_id),
        )
    return customer_balance(db, customer_id)


def job_escrow(db: WorkerDB, job_id: str) -> dict[str, Any] | None:
    row = db.conn.execute("SELECT * FROM job_escrows WHERE job_id = ?", (job_id,)).fetchone()
    if not row:
        return None
    return {
        "job_id": row["job_id"],
        "customer_id": row["customer_id"],
        "escrowed_qi": float(row["escrowed_qi"]),
        "settled_qi": float(row["settled_qi"]),
        "fee_qi": float(row["fee_qi"]),
        "worker_payout_qi": float(row["worker_payout_qi"]),
        "refunded_qi": float(row["refunded_qi"]),
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "metadata": json.loads(row["metadata_json"]),
    }


def settle_job_escrow(db: WorkerDB, job_id: str, worker_id: str, settled_qi: float, fee_percent: float) -> dict[str, Any]:
    escrow = job_escrow(db, job_id)
    if not escrow:
        now = utc_now_iso()
        payout = round(float(settled_qi), 12)
        with db.conn:
            _ensure_worker_account(db, worker_id, now)
            db.conn.execute(
                """
                UPDATE worker_accounts
                SET earned_qi = earned_qi + ?,
                    payable_qi = payable_qi + ?,
                    updated_at = ?
                WHERE worker_id = ?
                """,
                (payout, payout, now, worker_id),
            )
        return {
            "job_id": job_id,
            "status": "unescrowed",
            "settled_qi": payout,
            "fee_qi": 0.0,
            "worker_payout_qi": payout,
            "refund_qi": 0.0,
        }
    if escrow["status"] == "settled":
        return {
            "job_id": job_id,
            "status": "settled",
            "settled_qi": escrow["settled_qi"],
            "fee_qi": escrow["fee_qi"],
            "worker_payout_qi": escrow["worker_payout_qi"],
            "refund_qi": 0.0,
        }
    if escrow["status"] != "escrowed":
        raise ValueError(f"job escrow cannot be settled from status {escrow['status']}")
    settlement = min(float(settled_qi), escrow["escrowed_qi"])
    fee = round(settlement * max(float(fee_percent), 0.0) / 100.0, 12)
    worker_payout = round(settlement - fee, 12)
    refund = round(escrow["escrowed_qi"] - settlement, 12)
    now = utc_now_iso()
    with db.conn:
        account = customer_balance(db, escrow["customer_id"])
        if account["escrowed_qi"] + 1e-12 < escrow["escrowed_qi"]:
            raise ValueError("insufficient escrowed customer balance")
        db.conn.execute(
            """
            UPDATE customer_accounts
            SET escrowed_qi = escrowed_qi - ?,
                spent_qi = spent_qi + ?,
                available_qi = available_qi + ?,
                refunded_qi = refunded_qi + ?
            WHERE customer_id = ?
            """,
            (escrow["escrowed_qi"], settlement, refund, refund, escrow["customer_id"]),
        )
        db.conn.execute(
            """
            UPDATE job_escrows
            SET settled_qi = ?, fee_qi = ?, worker_payout_qi = ?,
                refunded_qi = ?, status = 'settled', updated_at = ?
            WHERE job_id = ?
            """,
            (settlement, fee, worker_payout, refund, now, job_id),
        )
        _ensure_worker_account(db, worker_id, now)
        db.conn.execute(
            """
            UPDATE worker_accounts
            SET earned_qi = earned_qi + ?,
                payable_qi = payable_qi + ?,
                updated_at = ?
            WHERE worker_id = ?
            """,
            (worker_payout, worker_payout, now, worker_id),
        )
    return {
        "job_id": job_id,
        "status": "settled",
        "settled_qi": round(settlement, 12),
        "fee_qi": fee,
        "worker_payout_qi": worker_payout,
        "refund_qi": refund,
    }


def refund_job_escrow(db: WorkerDB, job_id: str, reason: str = "refunded") -> dict[str, Any]:
    escrow = job_escrow(db, job_id)
    if not escrow:
        return {"job_id": job_id, "status": "unescrowed", "refund_qi": 0.0}
    if escrow["status"] in {"refunded", "settled"}:
        return {"job_id": job_id, "status": escrow["status"], "refund_qi": escrow["refunded_qi"]}
    now = utc_now_iso()
    refund = escrow["escrowed_qi"]
    with db.conn:
        refund_escrow(db, escrow["customer_id"], refund)
        db.conn.execute(
            """
            UPDATE job_escrows
            SET refunded_qi = ?, status = ?, updated_at = ?
            WHERE job_id = ?
            """,
            (refund, "disputed" if reason == "disputed" else "refunded", now, job_id),
        )
    return {"job_id": job_id, "status": "disputed" if reason == "disputed" else "refunded", "refund_qi": round(refund, 12)}


def worker_account(db: WorkerDB, worker_id: str) -> dict[str, Any]:
    _ensure_worker_account(db, worker_id, utc_now_iso())
    row = db.conn.execute("SELECT * FROM worker_accounts WHERE worker_id = ?", (worker_id,)).fetchone()
    return {
        "worker_id": row["worker_id"],
        "earned_qi": float(row["earned_qi"]),
        "payable_qi": float(row["payable_qi"]),
        "disputed_qi": float(row["disputed_qi"]),
        "rejected_qi": float(row["rejected_qi"]),
        "refunded_qi": float(row["refunded_qi"]),
        "updated_at": row["updated_at"],
    }


def record_worker_rejected(db: WorkerDB, worker_id: str, amount_qi: float, *, disputed: bool = False) -> None:
    now = utc_now_iso()
    with db.conn:
        _ensure_worker_account(db, worker_id, now)
        field = "disputed_qi" if disputed else "rejected_qi"
        db.conn.execute(
            f"UPDATE worker_accounts SET {field} = {field} + ?, updated_at = ? WHERE worker_id = ?",
            (float(amount_qi), now, worker_id),
        )


def _ensure_worker_account(db: WorkerDB, worker_id: str, now: str) -> None:
    db.conn.execute(
        """
        INSERT INTO worker_accounts (
            worker_id, earned_qi, payable_qi, disputed_qi, rejected_qi, refunded_qi, updated_at
        ) VALUES (?, 0, 0, 0, 0, 0, ?)
        ON CONFLICT(worker_id) DO NOTHING
        """,
        (worker_id, now),
    )
