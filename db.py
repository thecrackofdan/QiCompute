import json
import sqlite3
from pathlib import Path
from typing import Any

import failures
from lifecycle import transition_job_status


BALANCE_AFFECTING_EVENT_TYPES = {"inference_job", "mining_block_reward"}


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
    receipt_hash TEXT,
    job_id TEXT,
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

CREATE TABLE IF NOT EXISTS inference_jobs (
    job_id TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL,
    receipt_id TEXT NOT NULL,
    accepted_at TEXT NOT NULL,
    payout_event_id TEXT
);

CREATE TABLE IF NOT EXISTS worker_registry (
    worker_id TEXT PRIMARY KEY,
    operator TEXT,
    region TEXT,
    public_key TEXT,
    endpoint TEXT,
    hardware_profile_json TEXT NOT NULL,
    supported_modes_json TEXT NOT NULL,
    supported_models_json TEXT NOT NULL,
    gpu_count INTEGER NOT NULL DEFAULT 0,
    total_vram_gb REAL NOT NULL DEFAULT 0,
    total_watts_capacity REAL NOT NULL DEFAULT 0,
    online INTEGER NOT NULL DEFAULT 0,
    last_seen_at TEXT,
    reputation_score REAL NOT NULL DEFAULT 50,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    average_latency_ms REAL NOT NULL DEFAULT 0,
    average_energy_per_token REAL NOT NULL DEFAULT 0,
    current_jobs INTEGER NOT NULL DEFAULT 0,
    max_concurrent_jobs INTEGER NOT NULL DEFAULT 1,
    load_percent REAL NOT NULL DEFAULT 0,
    last_heartbeat_at TEXT,
    metadata_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customer_jobs (
    job_id TEXT PRIMARY KEY,
    customer_id TEXT,
    model TEXT NOT NULL,
    prompt_hash TEXT,
    input_tokens REAL NOT NULL,
    expected_output_tokens REAL NOT NULL,
    privacy_level TEXT NOT NULL,
    max_price_qi REAL NOT NULL,
    status TEXT NOT NULL,
    assigned_worker_id TEXT,
    route_score REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_failure_code TEXT,
    last_failure_reason TEXT,
    metadata_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS routing_audit_logs (
    audit_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    envelope_id TEXT,
    selected_worker_id TEXT,
    selected_score REAL NOT NULL,
    accepted INTEGER NOT NULL,
    reason TEXT NOT NULL,
    alternatives_json TEXT NOT NULL,
    router_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS challenges (
    challenge_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    challenge_type TEXT NOT NULL,
    expected_hash TEXT,
    expected_tokens REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    assigned_worker_id TEXT,
    verifier_worker_id TEXT,
    metadata_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS challenge_results (
    result_id TEXT PRIMARY KEY,
    challenge_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    receipt_id TEXT,
    worker_id TEXT,
    accepted INTEGER NOT NULL,
    reason TEXT NOT NULL,
    score REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
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
        self._migrate()
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def _migrate(self) -> None:
        receipt_columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(receipts)")}
        if "receipt_hash" not in receipt_columns:
            self.conn.execute("ALTER TABLE receipts ADD COLUMN receipt_hash TEXT")
        if "job_id" not in receipt_columns:
            self.conn.execute("ALTER TABLE receipts ADD COLUMN job_id TEXT")
        worker_columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(worker_registry)")}
        for column, ddl in {
            "current_jobs": "ALTER TABLE worker_registry ADD COLUMN current_jobs INTEGER NOT NULL DEFAULT 0",
            "max_concurrent_jobs": "ALTER TABLE worker_registry ADD COLUMN max_concurrent_jobs INTEGER NOT NULL DEFAULT 1",
            "load_percent": "ALTER TABLE worker_registry ADD COLUMN load_percent REAL NOT NULL DEFAULT 0",
            "last_heartbeat_at": "ALTER TABLE worker_registry ADD COLUMN last_heartbeat_at TEXT",
        }.items():
            if column not in worker_columns:
                self.conn.execute(ddl)
        job_columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(customer_jobs)")}
        for column, ddl in {
            "expires_at": "ALTER TABLE customer_jobs ADD COLUMN expires_at TEXT",
            "retry_count": "ALTER TABLE customer_jobs ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0",
            "last_failure_code": "ALTER TABLE customer_jobs ADD COLUMN last_failure_code TEXT",
            "last_failure_reason": "ALTER TABLE customer_jobs ADD COLUMN last_failure_reason TEXT",
        }.items():
            if column not in job_columns:
                self.conn.execute(ddl)

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
                receipt_id, receipt_hash, job_id, worker_id, mode, started_at, ended_at,
                duration_seconds, average_watts, energy_joules,
                output_type, output_amount, estimated_qi_owed, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                receipt["receipt_id"],
                receipt.get("receipt_hash"),
                receipt.get("metadata", {}).get("job_id"),
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

    def insert_challenge(self, challenge: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO challenges (
                challenge_id, job_id, challenge_type, expected_hash, expected_tokens,
                created_at, expires_at, assigned_worker_id, verifier_worker_id, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                challenge["challenge_id"],
                challenge["job_id"],
                challenge["challenge_type"],
                challenge.get("expected_hash"),
                float(challenge.get("expected_tokens", 0)),
                challenge["created_at"],
                challenge.get("expires_at"),
                challenge.get("assigned_worker_id"),
                challenge.get("verifier_worker_id"),
                json.dumps(challenge.get("metadata", {}), sort_keys=True),
            ),
        )
        self.conn.commit()

    def record_challenge_result(self, result: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO challenge_results (
                result_id, challenge_id, job_id, receipt_id, worker_id,
                accepted, reason, score, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result["result_id"],
                result["challenge_id"],
                result["job_id"],
                result.get("receipt_id"),
                result.get("worker_id"),
                1 if result.get("accepted", False) else 0,
                result["reason"],
                float(result.get("score", 0)),
                result["created_at"],
                json.dumps(result.get("metadata", {}), sort_keys=True),
            ),
        )
        self.conn.commit()

    def get_challenge(self, challenge_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM challenges WHERE challenge_id = ?",
            (challenge_id,),
        ).fetchone()
        return _challenge_row_to_dict(row) if row else None

    def challenge_results_for_job(self, job_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM challenge_results WHERE job_id = ? ORDER BY created_at ASC",
            (job_id,),
        )
        return [_challenge_result_row_to_dict(row) for row in rows]

    def inference_job_was_paid(self, job_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM inference_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        return row is not None

    def record_inference_job_paid(
        self,
        *,
        job_id: str,
        worker_id: str,
        receipt_id: str,
        accepted_at: str,
        payout_event_id: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO inference_jobs (
                job_id, worker_id, receipt_id, accepted_at, payout_event_id
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (job_id, worker_id, receipt_id, accepted_at, payout_event_id),
        )
        self.conn.commit()

    def insert_payout_event(self, event: dict[str, Any]) -> None:
        if event["event_type"] not in BALANCE_AFFECTING_EVENT_TYPES:
            raise ValueError(f"Unsupported balance-affecting event type: {event['event_type']}")
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

    def accepted_shares_for_pplns(self, target_weight: float) -> list[sqlite3.Row]:
        rows = self.conn.execute(
            """
            SELECT * FROM mining_shares
            WHERE accepted = 1 AND stale = 0 AND round_id IS NULL
            ORDER BY submitted_at DESC, share_id DESC
            """
        )
        shares = []
        total_weight = 0.0
        for row in rows:
            shares.append(row)
            total_weight += float(row["difficulty"])
            if total_weight >= target_weight:
                break
        return shares

    def assign_mining_shares_to_round(self, share_ids: list[str], round_id: str) -> None:
        if not share_ids:
            return
        with self.conn:
            self.conn.executemany(
                """
                UPDATE mining_shares
                SET round_id = ?
                WHERE share_id = ? AND round_id IS NULL
                """,
                [(round_id, share_id) for share_id in share_ids],
            )

    def mining_round_for_block_hash(self, block_hash: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM mining_rounds WHERE block_hash = ?",
            (block_hash,),
        ).fetchone()

    def get_settled_balance(self, worker_id: str) -> float:
        row = self.conn.execute(
            """
            SELECT COALESCE(SUM(qi_amount), 0) AS estimated_qi_owed
            FROM payout_events
            WHERE worker_id = ?
              AND event_type IN ('inference_job', 'mining_block_reward')
            """,
            (worker_id,),
        ).fetchone()
        return float(row["estimated_qi_owed"]) if row else 0.0

    def get_balance(self, worker_id: str) -> float:
        return self.get_settled_balance(worker_id)

    def get_estimated_receipt_total(self, worker_id: str) -> float:
        row = self.conn.execute(
            """
            SELECT COALESCE(SUM(estimated_qi_owed), 0) AS estimated_qi_owed
            FROM receipts
            WHERE worker_id = ?
            """,
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

    def register_worker(self, worker: dict[str, Any]) -> None:
        existing = self.get_worker(worker["worker_id"])
        reputation_score = existing["reputation_score"] if existing else float(worker.get("reputation_score", 50))
        success_count = existing["success_count"] if existing else int(worker.get("success_count", 0))
        failure_count = existing["failure_count"] if existing else int(worker.get("failure_count", 0))
        average_latency_ms = existing["average_latency_ms"] if existing else float(worker.get("average_latency_ms", 0))
        average_energy_per_token = (
            existing["average_energy_per_token"] if existing else float(worker.get("average_energy_per_token", 0))
        )
        now = worker.get("last_seen_at")
        self.conn.execute(
            """
            INSERT INTO worker_registry (
                worker_id, operator, region, public_key, endpoint,
                hardware_profile_json, supported_modes_json, supported_models_json,
                gpu_count, total_vram_gb, total_watts_capacity, online, last_seen_at,
                reputation_score, success_count, failure_count,
                average_latency_ms, average_energy_per_token,
                current_jobs, max_concurrent_jobs, load_percent, last_heartbeat_at,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(worker_id) DO UPDATE SET
                operator = excluded.operator,
                region = excluded.region,
                public_key = excluded.public_key,
                endpoint = excluded.endpoint,
                hardware_profile_json = excluded.hardware_profile_json,
                supported_modes_json = excluded.supported_modes_json,
                supported_models_json = excluded.supported_models_json,
                gpu_count = excluded.gpu_count,
                total_vram_gb = excluded.total_vram_gb,
                total_watts_capacity = excluded.total_watts_capacity,
                online = excluded.online,
                last_seen_at = excluded.last_seen_at,
                reputation_score = excluded.reputation_score,
                success_count = excluded.success_count,
                failure_count = excluded.failure_count,
                average_latency_ms = excluded.average_latency_ms,
                average_energy_per_token = excluded.average_energy_per_token,
                current_jobs = excluded.current_jobs,
                max_concurrent_jobs = excluded.max_concurrent_jobs,
                load_percent = excluded.load_percent,
                last_heartbeat_at = excluded.last_heartbeat_at,
                metadata_json = excluded.metadata_json
            """,
            (
                worker["worker_id"],
                worker.get("operator"),
                worker.get("region"),
                worker.get("public_key"),
                worker.get("endpoint"),
                json.dumps(worker.get("hardware_profile", {}), sort_keys=True),
                json.dumps(worker.get("supported_modes", []), sort_keys=True),
                json.dumps(worker.get("supported_models", []), sort_keys=True),
                int(worker.get("gpu_count", 0)),
                float(worker.get("total_vram_gb", 0)),
                float(worker.get("total_watts_capacity", 0)),
                1 if worker.get("online", False) else 0,
                now,
                reputation_score,
                success_count,
                failure_count,
                average_latency_ms,
                average_energy_per_token,
                int(worker.get("current_jobs", 0)),
                int(worker.get("max_concurrent_jobs", 1)),
                float(worker.get("load_percent", 0)),
                worker.get("last_heartbeat_at", now),
                json.dumps(worker.get("metadata", {}), sort_keys=True),
            ),
        )
        self.conn.commit()

    def update_worker_heartbeat(self, worker_id: str, telemetry: dict[str, Any]) -> None:
        worker = self.get_worker(worker_id)
        metadata = worker.get("metadata", {}) if worker else {}
        metadata.update(telemetry)
        self.conn.execute(
            """
            UPDATE worker_registry
            SET online = 1,
                last_seen_at = ?,
                last_heartbeat_at = ?,
                metadata_json = ?
            WHERE worker_id = ?
            """,
            (
                telemetry.get("last_seen_at"),
                telemetry.get("last_seen_at"),
                json.dumps(metadata, sort_keys=True),
                worker_id,
            ),
        )
        self.conn.commit()

    def get_worker(self, worker_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM worker_registry WHERE worker_id = ?",
            (worker_id,),
        ).fetchone()
        return _worker_row_to_dict(row) if row else None

    def list_online_workers(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM worker_registry WHERE online = 1 ORDER BY reputation_score DESC"
        )
        return [_worker_row_to_dict(row) for row in rows]

    def list_workers_for_model(self, model_name: str) -> list[dict[str, Any]]:
        return [
            worker
            for worker in self.list_online_workers()
            if model_name in worker.get("supported_models", [])
        ]

    def update_worker_reputation_stats(self, worker_id: str, stats: dict[str, Any]) -> None:
        self.conn.execute(
            """
            UPDATE worker_registry
            SET reputation_score = ?,
                success_count = ?,
                failure_count = ?,
                average_latency_ms = ?,
                average_energy_per_token = ?
            WHERE worker_id = ?
            """,
            (
                float(stats["reputation_score"]),
                int(stats["success_count"]),
                int(stats["failure_count"]),
                float(stats["average_latency_ms"]),
                float(stats["average_energy_per_token"]),
                worker_id,
            ),
        )
        self.conn.commit()

    def insert_customer_job(self, job: dict[str, Any]) -> None:
        now = job["created_at"]
        metadata = dict(job.get("metadata", {}))
        metadata.pop("prompt", None)
        metadata.pop("raw_prompt", None)
        self.conn.execute(
            """
            INSERT INTO customer_jobs (
                job_id, customer_id, model, prompt_hash, input_tokens,
                expected_output_tokens, privacy_level, max_price_qi, status,
                assigned_worker_id, route_score, created_at, updated_at, expires_at,
                retry_count, last_failure_code, last_failure_reason, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job["job_id"],
                job.get("customer_id"),
                job["model"],
                job.get("prompt_hash"),
                float(job.get("input_tokens", 0)),
                float(job.get("expected_output_tokens", 0)),
                job.get("privacy_level", "standard"),
                float(job.get("max_price_qi", 0)),
                job.get("status", "queued"),
                job.get("assigned_worker_id"),
                job.get("route_score"),
                now,
                job.get("updated_at", now),
                job.get("expires_at"),
                int(job.get("retry_count", 0)),
                job.get("last_failure_code"),
                job.get("last_failure_reason"),
                json.dumps(metadata, sort_keys=True),
            ),
        )
        self.conn.commit()

    def update_customer_job_status(self, job_id: str, status: str, metadata: dict[str, Any] | None = None) -> None:
        from receipts import utc_now_iso

        current = self.get_customer_job(job_id)
        if current and current["status"] != status and not transition_job_status(current["status"], status):
            raise ValueError(f"Invalid job status transition: {current['status']} -> {status}")
        merged = current.get("metadata", {}) if current else {}
        if metadata:
            merged.update({k: v for k, v in metadata.items() if k not in {"prompt", "raw_prompt"}})
        updated_at = metadata.get("updated_at") if metadata and metadata.get("updated_at") else utc_now_iso()
        self.conn.execute(
            """
            UPDATE customer_jobs
            SET status = ?, updated_at = ?, metadata_json = ?
            WHERE job_id = ?
            """,
            (status, updated_at, json.dumps(merged, sort_keys=True), job_id),
        )
        self.conn.commit()

    def assign_customer_job(self, job_id: str, worker_id: str, route_score: float) -> None:
        from receipts import utc_now_iso

        self.conn.execute(
            """
            UPDATE customer_jobs
            SET status = 'routed',
                assigned_worker_id = ?,
                route_score = ?,
                updated_at = ?
            WHERE job_id = ?
            """,
            (worker_id, route_score, utc_now_iso(), job_id),
        )
        self.conn.commit()

    def mark_customer_job_failure(self, job_id: str, failure_code: str, failure_reason: str, *, retrying: bool = False) -> None:
        from receipts import utc_now_iso

        current = self.get_customer_job(job_id)
        retry_count = int(current.get("retry_count", 0) or 0) + (1 if retrying else 0)
        status = "retrying" if retrying else "failed"
        if current and current["status"] != status and not transition_job_status(current["status"], status):
            if not (current["status"] == "running" and status in {"failed", "retrying"}):
                raise ValueError(f"Invalid job status transition: {current['status']} -> {status}")
        self.conn.execute(
            """
            UPDATE customer_jobs
            SET status = ?, retry_count = ?, last_failure_code = ?,
                last_failure_reason = ?, updated_at = ?
            WHERE job_id = ?
            """,
            (status, retry_count, failure_code, failure_reason, utc_now_iso(), job_id),
        )
        self.conn.commit()

    def get_customer_job(self, job_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM customer_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        return _customer_job_row_to_dict(row) if row else None

    def list_queued_jobs(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM customer_jobs WHERE status IN ('queued', 'retrying') ORDER BY created_at ASC"
        )
        return [_customer_job_row_to_dict(row) for row in rows]

    def expire_stale_customer_jobs(self, now: str) -> int:
        rows = self.conn.execute(
            """
            SELECT * FROM customer_jobs
            WHERE expires_at IS NOT NULL
              AND expires_at <= ?
              AND status IN ('queued', 'routed', 'running', 'retrying')
            """,
            (now,),
        ).fetchall()
        for row in rows:
            self.conn.execute(
                """
                UPDATE customer_jobs
                SET status = 'expired', updated_at = ?, last_failure_code = ?
                WHERE job_id = ?
                """,
                (now, failures.JOB_EXPIRED, row["job_id"]),
            )
        self.conn.commit()
        return len(rows)

    def update_worker_load(self, worker_id: str, current_jobs: int, max_concurrent_jobs: int) -> None:
        load_percent = 100.0 * current_jobs / max_concurrent_jobs if max_concurrent_jobs else 100.0
        self.conn.execute(
            """
            UPDATE worker_registry
            SET current_jobs = ?, max_concurrent_jobs = ?, load_percent = ?
            WHERE worker_id = ?
            """,
            (current_jobs, max_concurrent_jobs, load_percent, worker_id),
        )
        self.conn.commit()

    def increment_worker_load(self, worker_id: str) -> None:
        worker = self.get_worker(worker_id)
        if not worker:
            return
        self.update_worker_load(worker_id, int(worker["current_jobs"]) + 1, int(worker["max_concurrent_jobs"]))

    def decrement_worker_load(self, worker_id: str) -> None:
        worker = self.get_worker(worker_id)
        if not worker:
            return
        self.update_worker_load(worker_id, max(0, int(worker["current_jobs"]) - 1), int(worker["max_concurrent_jobs"]))

    def insert_routing_audit_log(self, log: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO routing_audit_logs (
                audit_id, job_id, envelope_id, selected_worker_id, selected_score,
                accepted, reason, alternatives_json, router_version, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                log["audit_id"],
                log["job_id"],
                log.get("envelope_id"),
                log.get("selected_worker_id"),
                float(log.get("selected_score", 0)),
                1 if log.get("accepted", False) else 0,
                log["reason"],
                json.dumps(log.get("alternatives", []), sort_keys=True),
                log.get("router_version", "local-v1"),
                log["created_at"],
                json.dumps(log.get("metadata", {}), sort_keys=True),
            ),
        )
        self.conn.commit()

    def recent_routing_audit_logs(self, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM routing_audit_logs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [_routing_audit_row_to_dict(row) for row in rows]

    def routing_audit_logs_for_job(self, job_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM routing_audit_logs WHERE job_id = ? ORDER BY created_at ASC",
            (job_id,),
        )
        return [_routing_audit_row_to_dict(row) for row in rows]


def _worker_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "worker_id": row["worker_id"],
        "operator": row["operator"],
        "region": row["region"],
        "public_key": row["public_key"],
        "endpoint": row["endpoint"],
        "hardware_profile": json.loads(row["hardware_profile_json"]),
        "supported_modes": json.loads(row["supported_modes_json"]),
        "supported_models": json.loads(row["supported_models_json"]),
        "gpu_count": row["gpu_count"],
        "total_vram_gb": row["total_vram_gb"],
        "total_watts_capacity": row["total_watts_capacity"],
        "online": bool(row["online"]),
        "last_seen_at": row["last_seen_at"],
        "reputation_score": row["reputation_score"],
        "success_count": row["success_count"],
        "failure_count": row["failure_count"],
        "average_latency_ms": row["average_latency_ms"],
        "average_energy_per_token": row["average_energy_per_token"],
        "current_jobs": row["current_jobs"],
        "max_concurrent_jobs": row["max_concurrent_jobs"],
        "load_percent": row["load_percent"],
        "last_heartbeat_at": row["last_heartbeat_at"],
        "metadata": json.loads(row["metadata_json"]),
    }


def _customer_job_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "job_id": row["job_id"],
        "customer_id": row["customer_id"],
        "model": row["model"],
        "prompt_hash": row["prompt_hash"],
        "input_tokens": row["input_tokens"],
        "expected_output_tokens": row["expected_output_tokens"],
        "privacy_level": row["privacy_level"],
        "max_price_qi": row["max_price_qi"],
        "status": row["status"],
        "assigned_worker_id": row["assigned_worker_id"],
        "route_score": row["route_score"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "expires_at": row["expires_at"],
        "retry_count": row["retry_count"],
        "last_failure_code": row["last_failure_code"],
        "last_failure_reason": row["last_failure_reason"],
        "metadata": json.loads(row["metadata_json"]),
    }


def _routing_audit_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "audit_id": row["audit_id"],
        "job_id": row["job_id"],
        "envelope_id": row["envelope_id"],
        "selected_worker_id": row["selected_worker_id"],
        "selected_score": row["selected_score"],
        "accepted": bool(row["accepted"]),
        "reason": row["reason"],
        "alternatives": json.loads(row["alternatives_json"]),
        "router_version": row["router_version"],
        "created_at": row["created_at"],
        "metadata": json.loads(row["metadata_json"]),
    }


def _challenge_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "challenge_id": row["challenge_id"],
        "job_id": row["job_id"],
        "challenge_type": row["challenge_type"],
        "expected_hash": row["expected_hash"],
        "expected_tokens": row["expected_tokens"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "assigned_worker_id": row["assigned_worker_id"],
        "verifier_worker_id": row["verifier_worker_id"],
        "metadata": json.loads(row["metadata_json"]),
    }


def _challenge_result_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "result_id": row["result_id"],
        "challenge_id": row["challenge_id"],
        "job_id": row["job_id"],
        "receipt_id": row["receipt_id"],
        "worker_id": row["worker_id"],
        "accepted": bool(row["accepted"]),
        "reason": row["reason"],
        "score": row["score"],
        "created_at": row["created_at"],
        "metadata": json.loads(row["metadata_json"]),
    }
