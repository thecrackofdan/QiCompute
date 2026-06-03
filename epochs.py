from __future__ import annotations

import json
from collections import defaultdict
from typing import Any
from uuid import uuid4

from db import WorkerDB
from receipts import utc_now_iso, verify_receipt_hash


def create_epoch(db: WorkerDB, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    epoch = {
        "epoch_id": str(uuid4()),
        "started_at": utc_now_iso(),
        "ended_at": None,
        "status": "active",
        "receipt_count": 0,
        "total_energy_joules": 0,
        "total_tokens": 0,
        "total_estimated_qi": 0,
        "total_settled_qi": 0,
        "total_verified_jobs": 0,
        "total_failed_jobs": 0,
        "metadata": metadata or {},
    }
    db.create_epoch(epoch)
    return epoch


def active_epoch(db: WorkerDB) -> dict[str, Any]:
    epoch = db.active_epoch()
    return epoch if epoch else create_epoch(db)


def finalize_epoch(db: WorkerDB, epoch_id: str) -> dict[str, Any]:
    current = db.epoch_summary(epoch_id)
    if not current:
        raise ValueError(f"Unknown epoch: {epoch_id}")
    if current["status"] == "finalized":
        raise ValueError(f"Epoch is already finalized: {epoch_id}")

    receipts = db.receipts_for_epoch(epoch_id)
    valid_receipts = [receipt for receipt in receipts if verify_receipt_hash(receipt)]
    payout_rows = db.conn.execute(
        """
        SELECT *
        FROM payout_events
        WHERE epoch_id = ?
          AND event_type IN ('inference_job', 'mining_block_reward')
        ORDER BY created_at ASC, event_id ASC
        """,
        (epoch_id,),
    ).fetchall()
    payouts = [_payout_row_to_dict(row) for row in payout_rows]
    receipt_ids = {receipt["receipt_id"] for receipt in valid_receipts}
    settled_payouts = [
        payout
        for payout in payouts
        if payout.get("source_id") in receipt_ids or payout["event_type"] == "mining_block_reward"
    ]

    challenge_rows = db.conn.execute(
        """
        SELECT cr.*
        FROM challenge_results cr
        JOIN receipts r ON r.receipt_id = cr.receipt_id
        JOIN payout_events p ON p.source_id = r.receipt_id
        WHERE p.epoch_id = ?
        ORDER BY cr.created_at ASC, cr.result_id ASC
        """,
        (epoch_id,),
    ).fetchall()
    challenge_results = [_challenge_result_row_to_dict(row) for row in challenge_rows]
    committee_counts = _committee_counts(db, epoch_id)
    worker_totals = _worker_totals(valid_receipts, settled_payouts)
    metadata = {
        "worker_totals": worker_totals,
        "reputation_deltas": {},
        "challenge_pass_count": sum(1 for result in challenge_results if result["accepted"]),
        "challenge_fail_count": sum(1 for result in challenge_results if not result["accepted"]),
        "accepted_committee_count": committee_counts["accepted"],
        "rejected_committee_count": committee_counts["rejected"],
        "disputed_committee_count": committee_counts["disputed"],
        "energy_totals": {"total_energy_joules": sum(float(receipt["energy_joules"]) for receipt in valid_receipts)},
        "payout_totals": {"total_settled_qi": sum(float(payout["qi_amount"]) for payout in settled_payouts)},
    }
    summary = {
        "epoch_id": epoch_id,
        "started_at": current["started_at"],
        "ended_at": utc_now_iso(),
        "receipt_count": len(valid_receipts),
        "total_energy_joules": round(sum(float(receipt["energy_joules"]) for receipt in valid_receipts), 8),
        "total_tokens": round(sum(float(receipt["output"]["amount"]) for receipt in valid_receipts), 8),
        "total_estimated_qi": round(sum(float(receipt["estimated_qi_owed"]) for receipt in valid_receipts), 12),
        "total_settled_qi": round(sum(float(payout["qi_amount"]) for payout in settled_payouts), 12),
        "total_verified_jobs": len(valid_receipts),
        "total_failed_jobs": metadata["challenge_fail_count"] + committee_counts["rejected"] + committee_counts["disputed"],
        "metadata": metadata,
    }
    db.finalize_epoch(summary)
    return db.epoch_summary(epoch_id)


def epoch_summary(db: WorkerDB, epoch_id: str) -> dict[str, Any] | None:
    return db.epoch_summary(epoch_id)


def receipts_for_epoch(db: WorkerDB, epoch_id: str) -> list[dict[str, Any]]:
    return db.receipts_for_epoch(epoch_id)


def _worker_totals(receipts: list[dict[str, Any]], payouts: list[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, dict[str, float]] = defaultdict(lambda: {"receipts": 0, "energy_joules": 0, "tokens": 0, "settled_qi": 0})
    for receipt in receipts:
        worker = receipt["worker_id"]
        totals[worker]["receipts"] += 1
        totals[worker]["energy_joules"] += float(receipt["energy_joules"])
        totals[worker]["tokens"] += float(receipt["output"]["amount"])
    for payout in payouts:
        totals[payout["worker_id"]]["settled_qi"] += float(payout["qi_amount"])
    return {worker: {key: round(value, 12) for key, value in data.items()} for worker, data in sorted(totals.items())}


def _committee_counts(db: WorkerDB, epoch_id: str) -> dict[str, int]:
    rows = db.conn.execute(
        """
        SELECT vc.result
        FROM verification_committees vc
        WHERE json_extract(vc.metadata_json, '$.epoch_id') = ?
        """,
        (epoch_id,),
    ).fetchall()
    counts = {"accepted": 0, "rejected": 0, "disputed": 0}
    for row in rows:
        if row["result"] in counts:
            counts[row["result"]] += 1
    return counts


def _payout_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "event_id": row["event_id"],
        "worker_id": row["worker_id"],
        "event_type": row["event_type"],
        "qi_amount": row["qi_amount"],
        "source_id": row["source_id"],
        "epoch_id": row["epoch_id"],
        "metadata": json.loads(row["metadata_json"]),
    }


def _challenge_result_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "result_id": row["result_id"],
        "accepted": bool(row["accepted"]),
        "reason": row["reason"],
        "metadata": json.loads(row["metadata_json"]),
    }
