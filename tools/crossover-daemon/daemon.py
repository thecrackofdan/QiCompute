"""Crossover daemon: point one GPU at whichever pays more, mining Quai or serving inference.

Standalone: `python3 daemon.py`. One config file, one SQLite log, no controller/worker split.
All money math is integer micro-USD and micro-Qi (1 unit = 1,000,000 micro). On any Quai
feed error the daemon defaults to mining.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import signal
import sqlite3
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from telemetry import GPUTelemetry


MICRO = 1_000_000
SECONDS_PER_DAY = 86_400
MODE_MINING = "mining"
MODE_INFERENCE = "inference"

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    mode_before TEXT NOT NULL,
    mode_after TEXT NOT NULL,
    switched INTEGER NOT NULL,
    reason TEXT NOT NULL,
    mining_net_usd_micro_per_day INTEGER NOT NULL,
    inference_net_usd_micro_per_day INTEGER NOT NULL,
    power_cost_usd_micro_per_day INTEGER NOT NULL,
    feeds_ok INTEGER NOT NULL,
    details_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(ts);

CREATE TABLE IF NOT EXISTS samples (
    sample_id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    mode TEXT NOT NULL,
    power_watts REAL,
    gpu_utilization_percent REAL,
    hashrate_hps INTEGER,
    tokens_per_second REAL
);
CREATE INDEX IF NOT EXISTS idx_samples_ts ON samples(ts);

CREATE TABLE IF NOT EXISTS inference_requests (
    request_id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL
);
"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Integer money helpers. Feeds and config hand us decimal strings or JSON
# numbers; convert once at the boundary via Decimal, integers everywhere else.
# ---------------------------------------------------------------------------

def to_micro(value: Any) -> int:
    return int(Decimal(str(value)) * MICRO)


def micro_to_str(micro: int) -> str:
    sign = "-" if micro < 0 else ""
    micro = abs(int(micro))
    return f"{sign}{micro // MICRO}.{micro % MICRO:06d}"


# ---------------------------------------------------------------------------
# Economics (pure integer functions; report.py and benchmark.py reuse these).
# ---------------------------------------------------------------------------

def mining_gross_usd_micro_per_day(
    *,
    hashrate_hps: int,
    network_difficulty: int,
    block_reward_micro_qi: int,
    qi_price_micro_usd: int,
) -> int:
    """Expected mining revenue: share of blocks/day times reward times price.

    Difficulty is the expected hashes per block, so blocks/day for this rig is
    hashrate * 86400 / difficulty.
    """
    if network_difficulty <= 0 or hashrate_hps <= 0:
        return 0
    micro_qi_per_day = hashrate_hps * SECONDS_PER_DAY * block_reward_micro_qi // network_difficulty
    return micro_qi_per_day * qi_price_micro_usd // MICRO


def inference_gross_usd_micro_per_day(*, rate_micro_usd_per_hour: int, utilization_percent: int) -> int:
    utilization = min(max(int(utilization_percent), 0), 100)
    return max(int(rate_micro_usd_per_hour), 0) * 24 * utilization // 100


def power_cost_usd_micro_per_day(*, watts: int, usd_per_kwh_micro: int) -> int:
    return max(int(watts), 0) * 24 * max(int(usd_per_kwh_micro), 0) // 1000


# ---------------------------------------------------------------------------
# Switching logic with hysteresis. Pure state machine, no I/O: this is the
# part under test.
# ---------------------------------------------------------------------------

class CrossoverEngine:
    """Decide which mode the GPU should be in, without flapping.

    A challenger must beat the incumbent by ``margin_percent`` of the
    incumbent's absolute net (or by ``margin_floor_usd_micro`` when the
    incumbent is near zero), for ``consecutive_decisions`` evaluations in a
    row, and no switch happens within ``min_dwell_seconds`` of the last one.
    Any Quai feed failure forces mining: the status quo a miner already runs.
    """

    def __init__(
        self,
        *,
        margin_percent: int = 15,
        consecutive_decisions: int = 3,
        min_dwell_seconds: int = 1800,
        margin_floor_usd_micro: int = 50_000,
        initial_mode: str = MODE_MINING,
    ):
        self.mode = initial_mode
        self.margin_percent = max(int(margin_percent), 0)
        self.consecutive_decisions = max(int(consecutive_decisions), 1)
        self.min_dwell_seconds = max(int(min_dwell_seconds), 0)
        self.margin_floor_usd_micro = max(int(margin_floor_usd_micro), 0)
        self.streak = 0
        self.last_switch_seconds: float | None = None

    def evaluate(
        self,
        *,
        mining_net_usd_micro: int,
        inference_net_usd_micro: int,
        feeds_ok: bool,
        now_seconds: float,
    ) -> dict[str, Any]:
        mode_before = self.mode
        if not feeds_ok:
            switched = self.mode != MODE_MINING
            if switched:
                self._switch(MODE_MINING, now_seconds)
            self.streak = 0
            return self._decision(mode_before, switched, "feed_failure_default_to_mining")

        challenger = MODE_INFERENCE if self.mode == MODE_MINING else MODE_MINING
        nets = {MODE_MINING: int(mining_net_usd_micro), MODE_INFERENCE: int(inference_net_usd_micro)}
        incumbent_net = nets[self.mode]
        challenger_net = nets[challenger]
        required_gain = max(abs(incumbent_net) * self.margin_percent // 100, self.margin_floor_usd_micro)
        if challenger_net >= incumbent_net + required_gain:
            self.streak += 1
        else:
            self.streak = 0
            return self._decision(mode_before, False, "incumbent_holds")
        if self.streak < self.consecutive_decisions:
            return self._decision(mode_before, False, f"challenger_streak_{self.streak}_of_{self.consecutive_decisions}")
        if (
            self.last_switch_seconds is not None
            and now_seconds - self.last_switch_seconds < self.min_dwell_seconds
        ):
            return self._decision(mode_before, False, "dwell_time_not_elapsed")
        self._switch(challenger, now_seconds)
        return self._decision(mode_before, True, f"{challenger}_beats_{mode_before}_by_margin")

    def _switch(self, mode: str, now_seconds: float) -> None:
        self.mode = mode
        self.streak = 0
        self.last_switch_seconds = now_seconds

    def _decision(self, mode_before: str, switched: bool, reason: str) -> dict[str, Any]:
        return {
            "mode_before": mode_before,
            "mode_after": self.mode,
            "switched": switched,
            "reason": reason,
            "streak": self.streak,
        }


# ---------------------------------------------------------------------------
# Feeds. Generic JSON-over-HTTP with a dotted path; any error returns ok=False.
# ---------------------------------------------------------------------------

def json_path(data: Any, path: str) -> Any:
    current = data
    for part in path.split("."):
        if isinstance(current, list):
            current = current[int(part)]
        else:
            current = current[part]
    return current


def fetch_feed(feed_cfg: dict[str, Any], timeout_seconds: float = 10.0) -> tuple[Any, bool, str]:
    """Fetch one configured feed. Returns (value, ok, error)."""
    url = str(feed_cfg.get("url", "") or "")
    if not url:
        return None, False, "feed url not configured"
    try:
        if str(feed_cfg.get("type", "get")) == "jsonrpc":
            payload = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": feed_cfg.get("method", ""),
                    "params": feed_cfg.get("params", []),
                }
            ).encode("utf-8")
            request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        else:
            request = urllib.request.Request(url, headers={"User-Agent": "qicompute-crossover-daemon"})
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
        value = json_path(data, str(feed_cfg.get("json_path", "")))
        return value, True, ""
    except Exception as exc:  # any feed problem is a fallback-to-mining event, never a crash
        return None, False, f"{type(exc).__name__}: {exc}"


def parse_difficulty(value: Any) -> int:
    if isinstance(value, str) and value.startswith("0x"):
        return int(value, 16)
    return int(Decimal(str(value)))


# ---------------------------------------------------------------------------
# SQLite log: WAL, cross-thread safe, idempotent writes via INSERT OR IGNORE
# on caller-supplied primary keys.
# ---------------------------------------------------------------------------

class CrossoverDB:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def record_decision(self, row: dict[str, Any]) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO decisions (
                    decision_id, ts, mode_before, mode_after, switched, reason,
                    mining_net_usd_micro_per_day, inference_net_usd_micro_per_day,
                    power_cost_usd_micro_per_day, feeds_ok, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["decision_id"],
                    row["ts"],
                    row["mode_before"],
                    row["mode_after"],
                    1 if row["switched"] else 0,
                    row["reason"],
                    int(row["mining_net_usd_micro_per_day"]),
                    int(row["inference_net_usd_micro_per_day"]),
                    int(row["power_cost_usd_micro_per_day"]),
                    1 if row["feeds_ok"] else 0,
                    json.dumps(row.get("details", {}), sort_keys=True),
                ),
            )

    def record_sample(self, row: dict[str, Any]) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO samples (
                    sample_id, ts, mode, power_watts, gpu_utilization_percent,
                    hashrate_hps, tokens_per_second
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["sample_id"],
                    row["ts"],
                    row["mode"],
                    row.get("power_watts"),
                    row.get("gpu_utilization_percent"),
                    row.get("hashrate_hps"),
                    row.get("tokens_per_second"),
                ),
            )

    def record_inference_request(self, row: dict[str, Any]) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO inference_requests (
                    request_id, ts, prompt_hash, input_tokens, output_tokens, duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row["request_id"],
                    row["ts"],
                    row["prompt_hash"],
                    int(row["input_tokens"]),
                    int(row["output_tokens"]),
                    int(row["duration_ms"]),
                ),
            )

    def decisions(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM decisions ORDER BY ts ASC").fetchall()
        return [dict(row) for row in rows]

    def latest_decision(self) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM decisions ORDER BY ts DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def close(self) -> None:
        self.conn.close()


# ---------------------------------------------------------------------------
# Subprocess management for the miner / inference backend.
# ---------------------------------------------------------------------------

class ManagedProcess:
    def __init__(self, name: str, command: list[str]):
        self.name = name
        self.command = [str(part) for part in (command or [])]
        self.process: subprocess.Popen | None = None

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self) -> None:
        if not self.command or self.running:
            return
        self.process = subprocess.Popen(
            self.command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def stop(self) -> None:
        if self.process is None or self.process.poll() is not None:
            self.process = None
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=10)
        self.process = None


# ---------------------------------------------------------------------------
# Ollama probe: measures serving throughput and logs hash + token counts only.
# ---------------------------------------------------------------------------

def probe_ollama(db: CrossoverDB, inference_cfg: dict[str, Any], timeout_seconds: float = 120.0) -> float | None:
    """Run one generation against local Ollama; returns tokens/sec or None.

    Only the prompt hash, token counts, and duration are persisted.
    """
    url = str(inference_cfg.get("ollama_url", "http://127.0.0.1:11434")).rstrip("/") + "/api/generate"
    prompt = str(inference_cfg.get("probe_prompt", "Briefly explain what a hash function does."))
    payload = json.dumps(
        {"model": inference_cfg.get("model", "llama3.1:8b"), "prompt": prompt, "stream": False}
    ).encode("utf-8")
    request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    duration_ms = int((time.perf_counter() - started) * 1000)
    output_tokens = int(data.get("eval_count", 0))
    eval_duration_ns = int(data.get("eval_duration", 0))
    tokens_per_second = output_tokens / (eval_duration_ns / 1e9) if eval_duration_ns > 0 else 0.0
    db.record_inference_request(
        {
            "request_id": str(uuid4()),
            "ts": utc_now_iso(),
            "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "input_tokens": int(data.get("prompt_eval_count", 0)),
            "output_tokens": output_tokens,
            "duration_ms": duration_ms,
        }
    )
    return round(tokens_per_second, 3)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config(path: str) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    import yaml  # type: ignore

    return yaml.safe_load(text)


# ---------------------------------------------------------------------------
# One decision cycle: gather inputs, evaluate, act, log.
# ---------------------------------------------------------------------------

def gather_economics(config: dict[str, Any], watts: int) -> dict[str, Any]:
    """Fetch feeds and compute integer net $/day for both paths.

    feeds_ok covers the Quai price and difficulty feeds only: without them
    mining cannot be priced, so the daemon falls back to mining. A failed
    inference market-rate feed degrades to the configured fallback rate.
    """
    mining_cfg = config.get("mining", {})
    inference_cfg = config.get("inference", {})
    power_cfg = config.get("power", {})
    usd_per_kwh_micro = to_micro(power_cfg.get("usd_per_kwh", "0.12"))
    power_cost = power_cost_usd_micro_per_day(watts=watts, usd_per_kwh_micro=usd_per_kwh_micro)

    price_value, price_ok, price_error = fetch_feed(mining_cfg.get("price_feed", {}))
    difficulty_value, difficulty_ok, difficulty_error = fetch_feed(mining_cfg.get("difficulty_feed", {}))
    feeds_ok = price_ok and difficulty_ok

    mining_gross = 0
    if feeds_ok:
        try:
            mining_gross = mining_gross_usd_micro_per_day(
                hashrate_hps=int(mining_cfg.get("fallback_hashrate_hps", 0)),
                network_difficulty=parse_difficulty(difficulty_value),
                block_reward_micro_qi=to_micro(mining_cfg.get("block_reward_qi", "0")),
                qi_price_micro_usd=to_micro(price_value),
            )
        except Exception as exc:
            feeds_ok = False
            price_error = price_error or f"{type(exc).__name__}: {exc}"

    rate_value, rate_ok, rate_error = fetch_feed(inference_cfg.get("market_rate_feed", {}))
    if rate_ok:
        try:
            rate_micro = to_micro(rate_value)
            rate_source = "feed"
        except Exception:
            rate_ok = False
    if not rate_ok:
        rate_micro = to_micro(inference_cfg.get("fallback_usd_per_hour", "0"))
        rate_source = "config_fallback"
    inference_gross = inference_gross_usd_micro_per_day(
        rate_micro_usd_per_hour=rate_micro,
        utilization_percent=int(inference_cfg.get("utilization_percent", 50)),
    )

    return {
        "feeds_ok": feeds_ok,
        "mining_net_usd_micro_per_day": mining_gross - power_cost,
        "inference_net_usd_micro_per_day": inference_gross - power_cost,
        "power_cost_usd_micro_per_day": power_cost,
        "details": {
            "watts": watts,
            "qi_price_feed_ok": price_ok,
            "qi_price_feed_error": price_error,
            "difficulty_feed_ok": difficulty_ok,
            "difficulty_feed_error": difficulty_error,
            "inference_rate_source": rate_source,
            "inference_rate_feed_error": rate_error if not rate_ok else "",
            "inference_rate_usd_micro_per_hour": rate_micro,
        },
    }


def run_cycle(
    *,
    config: dict[str, Any],
    db: CrossoverDB,
    engine: CrossoverEngine,
    telemetry: GPUTelemetry,
    miner: ManagedProcess,
    inference_backend: ManagedProcess,
    now_seconds: float,
    dry_run: bool = False,
) -> dict[str, Any]:
    watts = int(round(telemetry.total_watts()))
    economics = gather_economics(config, watts)
    decision = engine.evaluate(
        mining_net_usd_micro=economics["mining_net_usd_micro_per_day"],
        inference_net_usd_micro=economics["inference_net_usd_micro_per_day"],
        feeds_ok=economics["feeds_ok"],
        now_seconds=now_seconds,
    )
    if decision["switched"] and not dry_run:
        if decision["mode_after"] == MODE_MINING:
            inference_backend.stop()
            miner.start()
        else:
            miner.stop()
            inference_backend.start()
    row = {
        "decision_id": str(uuid4()),
        "ts": utc_now_iso(),
        **decision,
        "mining_net_usd_micro_per_day": economics["mining_net_usd_micro_per_day"],
        "inference_net_usd_micro_per_day": economics["inference_net_usd_micro_per_day"],
        "power_cost_usd_micro_per_day": economics["power_cost_usd_micro_per_day"],
        "feeds_ok": economics["feeds_ok"],
        "details": economics["details"],
    }
    db.record_decision(row)
    db.record_sample(
        {
            "sample_id": str(uuid4()),
            "ts": row["ts"],
            "mode": decision["mode_after"],
            "power_watts": float(watts),
            "gpu_utilization_percent": None,
            "hashrate_hps": int(config.get("mining", {}).get("fallback_hashrate_hps", 0))
            if decision["mode_after"] == MODE_MINING
            else None,
            "tokens_per_second": None,
        }
    )
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Quai mining vs inference crossover daemon")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--once", action="store_true", help="Run one decision cycle and exit")
    parser.add_argument("--status", action="store_true", help="Print the latest decision and exit")
    parser.add_argument("--dry-run", action="store_true", help="Decide and log, but never start/stop processes")
    args = parser.parse_args()
    config = load_config(args.config)
    daemon_cfg = config.get("daemon", {})
    db = CrossoverDB(str(daemon_cfg.get("db_path", "crossover.db")))

    if args.status:
        latest = db.latest_decision()
        print(json.dumps(latest, indent=2) if latest else "no decisions logged yet")
        db.close()
        return 0

    switching_cfg = config.get("switching", {})
    engine = CrossoverEngine(
        margin_percent=int(switching_cfg.get("margin_percent", 15)),
        consecutive_decisions=int(switching_cfg.get("consecutive_decisions", 3)),
        min_dwell_seconds=int(switching_cfg.get("min_dwell_seconds", 1800)),
        margin_floor_usd_micro=to_micro(switching_cfg.get("margin_floor_usd_per_day", "0.05")),
    )
    telemetry = GPUTelemetry(
        nvidia_smi_path=str(config.get("gpu", {}).get("nvidia_smi_path", "nvidia-smi")),
        fallback_watts=float(config.get("power", {}).get("fallback_watts", 300)),
    )
    miner = ManagedProcess("miner", config.get("mining", {}).get("miner_command", []))
    inference_backend = ManagedProcess("inference", config.get("inference", {}).get("backend_command", []))
    interval = max(int(daemon_cfg.get("decision_interval_seconds", 60)), 5)
    probe_interval = max(int(config.get("inference", {}).get("probe_interval_seconds", 300)), interval)
    last_probe = 0.0

    if not args.dry_run and engine.mode == MODE_MINING:
        miner.start()

    stop_requested = False

    def _handle_signal(_signum, _frame):
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        while True:
            now = time.monotonic()
            row = run_cycle(
                config=config,
                db=db,
                engine=engine,
                telemetry=telemetry,
                miner=miner,
                inference_backend=inference_backend,
                now_seconds=now,
                dry_run=args.dry_run,
            )
            print(
                f"{row['ts']} mode={row['mode_after']} switched={row['switched']} "
                f"reason={row['reason']} mining=${micro_to_str(row['mining_net_usd_micro_per_day'])}/day "
                f"inference=${micro_to_str(row['inference_net_usd_micro_per_day'])}/day"
            )
            if engine.mode == MODE_INFERENCE and now - last_probe >= probe_interval and not args.dry_run:
                tokens_per_second = probe_ollama(db, config.get("inference", {}))
                last_probe = now
                if tokens_per_second is not None:
                    print(f"  inference probe: {tokens_per_second} tokens/sec")
            if args.once or stop_requested:
                break
            time.sleep(interval)
    finally:
        miner.stop()
        inference_backend.stop()
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
