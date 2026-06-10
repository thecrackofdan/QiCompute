"""Claim 4: why Qi and not just a kWh index? Because an index quotes and money settles.

A kWh index can tell you what compute should cost; it cannot be escrowed,
transferred, or settled. This script is the minimal demonstration, salvaged
from the QiCompute marketplace with its audit fixes applied: integer micro-Qi
everywhere, SQLite in WAL mode with check_same_thread=False, and idempotent
writes (re-running a settlement cannot double-pay).

    python3 claim4_settlement.py --demo      # full job lifecycle, printed ledger

Flow: price an inference job from the live index (claim 1's Qi/joule x
claim 3's joules/token) -> escrow the quote from the customer -> record the
served output (prompt hash + token counts only) -> settle pro-rata to tokens
actually served, refunding the customer the difference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from fetch_data import load_research_config
from qi_index import MICRO, current_index, qi_micro_for_tokens


SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    balance_micro_qi INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    created_ts TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    quoted_tokens INTEGER NOT NULL,
    quoted_micro_qi INTEGER NOT NULL,
    escrowed_micro_qi INTEGER NOT NULL,
    served_tokens INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    settled_micro_qi INTEGER NOT NULL DEFAULT 0,
    refunded_micro_qi INTEGER NOT NULL DEFAULT 0,
    settled_ts TEXT
);
"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SettlementLedger:
    def __init__(self, path: str = "settlement.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def ensure_account(self, account_id: str, opening_micro_qi: int = 0) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO accounts (account_id, balance_micro_qi) VALUES (?, ?)",
                (account_id, int(opening_micro_qi)),
            )

    def balance(self, account_id: str) -> int:
        row = self.conn.execute(
            "SELECT balance_micro_qi FROM accounts WHERE account_id = ?", (account_id,)
        ).fetchone()
        return int(row[0]) if row else 0

    def quote_and_escrow(
        self,
        *,
        job_id: str,
        customer_id: str,
        worker_id: str,
        prompt: str,
        tokens: int,
        joules_per_token: float,
        joules_per_qi_value: float,
    ) -> dict[str, Any]:
        """Quote a job at the live index and escrow that amount from the customer.

        Idempotent on job_id: re-running an existing job is a no-op.
        """
        quote_micro = qi_micro_for_tokens(
            tokens=tokens, joules_per_token=joules_per_token, joules_per_qi_value=joules_per_qi_value
        )
        with self.conn:
            existing = self.conn.execute("SELECT job_id FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if existing:
                return self.job(job_id)
            balance = self.balance(customer_id)
            if balance < quote_micro:
                raise ValueError(
                    f"insufficient balance: customer has {balance} micro-Qi, quote is {quote_micro}"
                )
            self.conn.execute(
                "UPDATE accounts SET balance_micro_qi = balance_micro_qi - ? WHERE account_id = ?",
                (quote_micro, customer_id),
            )
            self.conn.execute(
                """
                INSERT INTO jobs (
                    job_id, created_ts, customer_id, worker_id, prompt_hash,
                    quoted_tokens, quoted_micro_qi, escrowed_micro_qi, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'escrowed')
                """,
                (
                    job_id,
                    utc_now_iso(),
                    customer_id,
                    worker_id,
                    hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                    int(tokens),
                    quote_micro,
                    quote_micro,
                ),
            )
        return self.job(job_id)

    def record_served(self, job_id: str, served_tokens: int) -> dict[str, Any]:
        with self.conn:
            self.conn.execute(
                "UPDATE jobs SET served_tokens = ?, status = 'served' WHERE job_id = ? AND status = 'escrowed'",
                (int(served_tokens), job_id),
            )
        return self.job(job_id)

    def settle(self, job_id: str) -> dict[str, Any]:
        """Pay the worker pro-rata to tokens served; refund the rest. Idempotent.

        The status guard makes re-running a settlement a no-op: money moves
        exactly once per job, the double-pay fix carried over from QiCompute.
        """
        with self.conn:
            job = self.conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if job is None:
                raise ValueError(f"unknown job: {job_id}")
            if job["status"] == "settled":
                return self.job(job_id)
            if job["status"] not in {"served", "escrowed"}:
                raise ValueError(f"job not settleable from status {job['status']}")
            served = min(int(job["served_tokens"]), int(job["quoted_tokens"]))
            escrow = int(job["escrowed_micro_qi"])
            payout = escrow * served // int(job["quoted_tokens"]) if job["quoted_tokens"] > 0 else 0
            refund = escrow - payout
            self.conn.execute(
                "UPDATE accounts SET balance_micro_qi = balance_micro_qi + ? WHERE account_id = ?",
                (payout, job["worker_id"]),
            )
            self.conn.execute(
                "UPDATE accounts SET balance_micro_qi = balance_micro_qi + ? WHERE account_id = ?",
                (refund, job["customer_id"]),
            )
            self.conn.execute(
                """
                UPDATE jobs SET status = 'settled', settled_micro_qi = ?, refunded_micro_qi = ?, settled_ts = ?
                WHERE job_id = ?
                """,
                (payout, refund, utc_now_iso(), job_id),
            )
        return self.job(job_id)

    def job(self, job_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return dict(row) if row else {}

    def total_micro_qi(self) -> int:
        accounts = self.conn.execute("SELECT COALESCE(SUM(balance_micro_qi), 0) FROM accounts").fetchone()[0]
        escrowed = self.conn.execute(
            "SELECT COALESCE(SUM(escrowed_micro_qi), 0) FROM jobs WHERE status IN ('escrowed', 'served')"
        ).fetchone()[0]
        return int(accounts) + int(escrowed)

    def close(self) -> None:
        self.conn.close()


def run_demo(config: dict[str, Any], *, db_path: str, sample: bool) -> int:
    index = current_index(config, sample=sample)
    if index is None:
        print("no difficulty cache; run `python3 fetch_data.py` (or use --sample)")
        return 1
    ledger = SettlementLedger(db_path)
    ledger.ensure_account("customer-demo", opening_micro_qi=10 * MICRO)
    ledger.ensure_account("worker-demo", opening_micro_qi=0)
    before = ledger.total_micro_qi()
    jpq = float(index["joules_per_qi"])
    job = ledger.quote_and_escrow(
        job_id="demo-job-1",
        customer_id="customer-demo",
        worker_id="worker-demo",
        prompt="Demo prompt: summarize the energy-money thesis.",
        tokens=int(index["tokens"]),
        joules_per_token=float(index["joules_per_token"]),
        joules_per_qi_value=jpq,
    )
    print(f"quoted+escrowed: {job['quoted_micro_qi']} micro-Qi for {job['quoted_tokens']:,} tokens "
          f"(index as of {index['as_of']}{' SYNTHETIC' if sample else ''})")
    ledger.record_served("demo-job-1", served_tokens=int(index["tokens"]) * 80 // 100)
    settled = ledger.settle("demo-job-1")
    settled_again = ledger.settle("demo-job-1")  # idempotent: no double pay
    assert settled["settled_micro_qi"] == settled_again["settled_micro_qi"]
    after = ledger.total_micro_qi()
    print(f"served 80% of quoted tokens -> worker paid {settled['settled_micro_qi']} micro-Qi, "
          f"customer refunded {settled['refunded_micro_qi']} micro-Qi")
    print(f"customer balance: {ledger.balance('customer-demo')} micro-Qi")
    print(f"worker balance:   {ledger.balance('worker-demo')} micro-Qi")
    print(f"conservation: {before} micro-Qi before == {after} after: {before == after}")
    print("why Qi and not a kWh index: the index produced the quote; only money could escrow and settle it.")
    ledger.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Claim 4: minimal Qi settlement demo")
    parser.add_argument("--config", default="research.yaml")
    parser.add_argument("--db", default="settlement.db")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--sample", action="store_true", help="Use synthetic sample fixtures (testing only)")
    args = parser.parse_args()
    if not args.demo:
        print("use --demo to run the job lifecycle demonstration")
        return 1
    config = load_research_config(args.config)
    return run_demo(config, db_path=args.db, sample=args.sample)


if __name__ == "__main__":
    raise SystemExit(main())
