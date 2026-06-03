from __future__ import annotations

import argparse
from typing import Any

from db import WorkerDB
from worker import load_config


def table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "(none)"
    widths = {column: max(len(column), *(len(str(row.get(column, ""))) for row in rows)) for column in columns}
    header = "  ".join(column.ljust(widths[column]) for column in columns)
    body = ["  ".join(str(row.get(column, "")).ljust(widths[column]) for column in columns) for row in rows]
    return "\n".join([header, *body])


def command_rows(db: WorkerDB, command: str) -> tuple[list[dict[str, Any]], list[str]]:
    if command == "workers":
        rows = [dict(row) for row in db.conn.execute("SELECT worker_id, online, reputation_score, current_jobs, max_concurrent_jobs, load_percent FROM worker_registry ORDER BY worker_id")]
        return rows, ["worker_id", "online", "reputation_score", "current_jobs", "max_concurrent_jobs", "load_percent"]
    if command == "jobs":
        rows = [dict(row) for row in db.conn.execute("SELECT job_id, status, assigned_worker_id, lease_id, lease_expires_at FROM customer_jobs ORDER BY created_at DESC LIMIT 20")]
        return rows, ["job_id", "status", "assigned_worker_id", "lease_id", "lease_expires_at"]
    if command == "epochs":
        rows = [dict(row) for row in db.conn.execute("SELECT epoch_id, status, receipt_count, total_settled_qi FROM settlement_epochs ORDER BY started_at DESC LIMIT 10")]
        return rows, ["epoch_id", "status", "receipt_count", "total_settled_qi"]
    if command == "receipts":
        rows = [dict(row) for row in db.conn.execute("SELECT receipt_id, job_id, worker_id, mode, estimated_qi_owed FROM receipts ORDER BY ended_at DESC LIMIT 20")]
        return rows, ["receipt_id", "job_id", "worker_id", "mode", "estimated_qi_owed"]
    if command == "committees":
        rows = [dict(row) for row in db.conn.execute("SELECT committee_id, challenge_id, result, quorum_threshold FROM verification_committees ORDER BY created_at DESC LIMIT 20")]
        return rows, ["committee_id", "challenge_id", "result", "quorum_threshold"]
    rows = [dict(row) for row in db.conn.execute("SELECT event_type, worker_id, job_id, accepted, failure_code FROM cluster_events ORDER BY created_at DESC LIMIT 20")]
    return rows, ["event_type", "worker_id", "job_id", "accepted", "failure_code"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect local QiCompute cluster state")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("command", choices=["workers", "jobs", "epochs", "receipts", "committees", "events"])
    args = parser.parse_args()
    config = load_config(args.config)
    db = WorkerDB(config["worker"]["db_path"])
    try:
        rows, columns = command_rows(db, args.command)
        print(table(rows, columns))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
