from __future__ import annotations

import argparse
from typing import Any

from accounting_checks import run_accounting_checks
from db import WorkerDB
from worker import load_config


def recent_attacks(db: WorkerDB) -> list[dict[str, Any]]:
    rows = db.conn.execute(
        """
        SELECT event_type, worker_id, job_id, failure_code, created_at
        FROM cluster_events
        WHERE failure_code IN (
            'DUPLICATE_RECEIPT', 'STALE_RECEIPT', 'RATE_LIMITED',
            'AUTH_FAILED', 'ESCROW_UNDERFUNDED', 'ESCROW_LIMIT_EXCEEDED'
        )
        ORDER BY created_at DESC
        LIMIT 20
        """
    )
    return [dict(row) for row in rows]


def suspicious_committees(db: WorkerDB) -> list[dict[str, Any]]:
    rows = db.conn.execute(
        """
        SELECT committee_id, result, metadata_json
        FROM verification_committees
        WHERE json_extract(metadata_json, '$.collusion_suspicion_score') > 0
        ORDER BY created_at DESC
        LIMIT 20
        """
    )
    return [dict(row) for row in rows]


def duplicate_receipts(db: WorkerDB) -> list[dict[str, Any]]:
    rows = db.conn.execute(
        """
        SELECT receipt_hash, COUNT(*) AS count
        FROM receipts
        WHERE receipt_hash IS NOT NULL
        GROUP BY receipt_hash
        HAVING COUNT(*) > 1
        """
    )
    return [dict(row) for row in rows]


def print_rows(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("(none)")
        return
    for row in rows:
        print(" ".join(f"{key}={value}" for key, value in row.items()))


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit local QiCompute abuse and accounting signals")
    parser.add_argument("--config", default="config.marketplace.yaml")
    parser.add_argument("--recent-attacks", action="store_true")
    parser.add_argument("--reconciliation", action="store_true")
    parser.add_argument("--suspicious-committees", action="store_true")
    parser.add_argument("--duplicate-receipts", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    db = WorkerDB(config["worker"]["db_path"])
    try:
        if args.reconciliation:
            for check in run_accounting_checks(db):
                print(f"{check.status} {check.name}: {check.details}")
        if args.suspicious_committees:
            print_rows(suspicious_committees(db))
        if args.duplicate_receipts:
            print_rows(duplicate_receipts(db))
        if args.recent_attacks or not any((args.reconciliation, args.suspicious_committees, args.duplicate_receipts)):
            print_rows(recent_attacks(db))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
