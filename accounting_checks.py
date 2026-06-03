from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any

from db import WorkerDB
from treasury import get_treasury
from worker import load_config


@dataclass(frozen=True)
class AccountingCheck:
    name: str
    status: str
    details: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "details": self.details}


def run_accounting_checks(db: WorkerDB) -> list[AccountingCheck]:
    checks = [
        _customer_escrow_reconciles(db),
        _worker_payables_reconcile(db),
        _treasury_reconciles(db),
        _duplicate_receipts_not_paid(db),
    ]
    return checks


def _customer_escrow_reconciles(db: WorkerDB) -> AccountingCheck:
    account_total = _sum(db, "SELECT COALESCE(SUM(escrowed_qi), 0) FROM customer_accounts")
    escrow_total = _sum(db, "SELECT COALESCE(SUM(escrowed_qi), 0) FROM job_escrows WHERE status = 'escrowed'")
    return _compare("customer escrow totals", account_total, escrow_total)


def _worker_payables_reconcile(db: WorkerDB) -> AccountingCheck:
    account_total = _sum(db, "SELECT COALESCE(SUM(payable_qi), 0) FROM worker_accounts")
    escrow_total = _sum(db, "SELECT COALESCE(SUM(worker_payout_qi), 0) FROM job_escrows WHERE status = 'settled'")
    return _compare("worker payable totals", account_total, escrow_total)


def _treasury_reconciles(db: WorkerDB) -> AccountingCheck:
    treasury = get_treasury(db)
    fee_total = _sum(db, "SELECT COALESCE(SUM(fee_qi), 0) FROM job_escrows WHERE status = 'settled'")
    refund_total = _sum(db, "SELECT COALESCE(SUM(refunded_qi), 0) FROM job_escrows WHERE status IN ('settled', 'refunded', 'disputed')")
    ok = abs(treasury["total_fees_collected"] - fee_total) < 1e-12 and abs(treasury["total_customer_refunds"] - refund_total) < 1e-12
    return AccountingCheck(
        "treasury totals",
        "PASS" if ok else "FAIL",
        f"fees={treasury['total_fees_collected']:.12f}/{fee_total:.12f} refunds={treasury['total_customer_refunds']:.12f}/{refund_total:.12f}",
    )


def _duplicate_receipts_not_paid(db: WorkerDB) -> AccountingCheck:
    duplicates = db.conn.execute(
        """
        SELECT job_id, COUNT(*) AS count
        FROM inference_jobs
        GROUP BY job_id
        HAVING COUNT(*) > 1
        """
    ).fetchall()
    return AccountingCheck("duplicate paid jobs", "PASS" if not duplicates else "FAIL", f"duplicates={len(duplicates)}")


def _compare(name: str, left: float, right: float) -> AccountingCheck:
    ok = abs(left - right) < 1e-12
    return AccountingCheck(name, "PASS" if ok else "FAIL", f"{left:.12f} vs {right:.12f}")


def _sum(db: WorkerDB, sql: str) -> float:
    row = db.conn.execute(sql).fetchone()
    return float(row[0] if row else 0.0)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local QiCompute marketplace accounting")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    config = load_config(args.config)
    db = WorkerDB(config["worker"]["db_path"])
    try:
        checks = run_accounting_checks(db)
        for check in checks:
            print(f"{check.status} {check.name}: {check.details}")
        return 0 if all(check.status != "FAIL" for check in checks) else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
