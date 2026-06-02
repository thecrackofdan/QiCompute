import json
import sqlite3
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    gpu_index INTEGER,
    name TEXT,
    power_watts REAL,
    temperature_c REAL,
    utilization_gpu_percent REAL,
    utilization_memory_percent REAL,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS receipts (
    receipt_id TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    average_watts REAL NOT NULL,
    energy_joules REAL NOT NULL,
    output_type TEXT NOT NULL,
    output_amount REAL NOT NULL,
    estimated_qi_owed REAL NOT NULL,
    metadata_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS balances (
    worker_id TEXT PRIMARY KEY,
    estimated_qi_owed REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payout_events (
    event_id TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    basis TEXT NOT NULL,
    qi_amount REAL NOT NULL,
    created_at TEXT NOT NULL,
    source_id TEXT,
    metadata_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mining_shares (
    share_id TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    difficulty REAL NOT NULL,
    accepted INTEGER NOT NULL,
    stale INTEGER NOT NULL DEFAULT 0,
    round_id TEXT,
    receipt_id TEXT,
    metadata_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mining_rounds (
    round_id TEXT PRIMARY KEY,
    block_hash TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    reward_qi REAL NOT NULL,
    pool_fee_qi REAL NOT NULL,
    net_reward_qi REAL NOT NULL,
    policy TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_mining_rounds_block_hash
ON mining_rounds(block_hash)
WHERE block_hash IS NOT NULL;
"""


class WorkerDB:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def insert_telemetry(self, sample: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO telemetry (
                ts, gpu_index, name, power_watts, temperature_c,
                utilization_gpu_percent, utilization_memory_percent, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sample.get("ts"),
                sample.get("gpu_index"),
                sample.get("name"),
                sample.get("power_watts"),
                sample.get("temperature_c"),
                sample.get("utilization_gpu_percent"),
                sample.get("utilization_memory_percent"),
                json.dumps(sample, sort_keys=True),
            ),
        )
        self.conn.commit()

    def insert_receipt(self, receipt: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO receipts (
                receipt_id, worker_id, mode, started_at, ended_at,
                duration_seconds, average_watts, energy_joules,
                output_type, output_amount, estimated_qi_owed, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                receipt["receipt_id"],
                receipt["worker_id"],
                receipt["mode"],
                receipt["started_at"],
                receipt["ended_at"],
                receipt["duration_seconds"],
                receipt["average_watts"],
                receipt["energy_joules"],
                receipt["output"]["type"],
                receipt["output"]["amount"],
                receipt["estimated_qi_owed"],
                json.dumps(receipt.get("metadata", {}), sort_keys=True),
            ),
        )
        self.conn.commit()

    def insert_payout_event(self, event: dict[str, Any]) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO payout_events (
                    event_id, worker_id, event_type, basis, qi_amount,
                    created_at, source_id, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["event_id"],
                    event["worker_id"],
                    event["event_type"],
                    event["basis"],
                    event["qi_amount"],
                    event["created_at"],
                    event.get("source_id"),
                    json.dumps(event.get("metadata", {}), sort_keys=True),
                ),
            )
            self.conn.execute(
                """
                INSERT INTO balances (worker_id, estimated_qi_owed, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(worker_id) DO UPDATE SET
                    estimated_qi_owed = estimated_qi_owed + excluded.estimated_qi_owed,
                    updated_at = excluded.updated_at
                """,
                (
                    event["worker_id"],
                    event["qi_amount"],
                    event["created_at"],
                ),
            )

    def insert_mining_share(self, share: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO mining_shares (
                share_id, worker_id, submitted_at, difficulty, accepted,
                stale, round_id, receipt_id, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                share["share_id"],
                share["worker_id"],
                share["submitted_at"],
                share["difficulty"],
                1 if share.get("accepted", True) else 0,
                1 if share.get("stale", False) else 0,
                share.get("round_id"),
                share.get("receipt_id"),
                json.dumps(share.get("metadata", {}), sort_keys=True),
            ),
        )
        self.conn.commit()

    def insert_mining_round(self, round_data: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO mining_rounds (
                round_id, block_hash, started_at, ended_at, reward_qi,
                pool_fee_qi, net_reward_qi, policy, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                round_data["round_id"],
                round_data.get("block_hash"),
                round_data["started_at"],
                round_data["ended_at"],
                round_data["reward_qi"],
                round_data["pool_fee_qi"],
                round_data["net_reward_qi"],
                round_data["policy"],
                json.dumps(round_data.get("metadata", {}), sort_keys=True),
            ),
        )
        self.conn.commit()

    def accepted_shares_for_pplns(self, limit: int) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT * FROM mining_shares
                WHERE accepted = 1 AND stale = 0
                ORDER BY submitted_at DESC, share_id DESC
                LIMIT ?
                """,
                (limit,),
            )
        )

    def mining_round_for_block_hash(self, block_hash: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM mining_rounds WHERE block_hash = ?",
            (block_hash,),
        ).fetchone()

    def get_balance(self, worker_id: str) -> float:
        row = self.conn.execute(
            "SELECT estimated_qi_owed FROM balances WHERE worker_id = ?",
            (worker_id,),
        ).fetchone()
        return float(row["estimated_qi_owed"]) if row else 0.0

    def recent_receipts(self, limit: int = 10) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT * FROM receipts ORDER BY ended_at DESC LIMIT ?",
                (limit,),
            )
        )

    def recent_payout_events(self, limit: int = 10) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT * FROM payout_events ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        )
