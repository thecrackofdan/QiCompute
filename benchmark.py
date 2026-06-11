"""Claim 3 measurement: joules/token on this rig, plus reference-rig calibration.

    python3 benchmark.py --minutes 5 --store          # measure inference, store to measurements.db
    python3 benchmark.py --calibrate-rig --minutes 5  # measure mining hashrate+watts for research.yaml

MEASUREMENT BOUNDARY (claim 3 methodology - report this with any number):
joules/token here is MARGINAL GPU BOARD DRAW divided by token throughput.
- Included: GPU board power as reported by NVML/nvidia-smi, averaged over
  the inference phase.
- Excluded: CPU, RAM, fans, storage, PSU conversion losses, networking.
- Idle/baseline GPU power is NOT subtracted (the GPU is presumed dedicated
  to the workload while serving).
- PUE = 1.0 is assumed (home rig: no datacenter cooling/distribution
  overhead). State a different PUE explicitly if measuring in a facility.
- Batch size 1, single request stream; quantization and context length are
  whatever the configured Ollama model serves - record the model tag.
These choices can swing joules/token 2-5x; rows with different boundaries
must not be pooled (PREDICTIONS.md P3). The boundary string is stored in
each row's notes so the public dataset stays comparable.

--calibrate-rig runs the configured Quai miner instead, parses live hashrate
from its stdout, samples watts, and prints the reference_gpu block to paste
into research.yaml - the rig behind claim 1's modeled cost of production.

This script measures physics only (tokens/sec, watts, joules/token,
hashes/sec). Qi-denominated derivations live in qi_index.py; this script
quotes no fiat prices.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fetch_data import load_research_config
from telemetry import GPUTelemetry


MEASUREMENT_BOUNDARY = (
    "marginal GPU board draw (NVML), no idle subtraction, excludes CPU/RAM/fans/PSU, PUE=1.0, batch=1"
)

MEASUREMENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS measurements (
    measurement_id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    gpu_name TEXT,
    gpu_count INTEGER,
    driver_version TEXT,
    vram_total_mb REAL,
    backend TEXT NOT NULL,
    model_name TEXT NOT NULL,
    minutes REAL NOT NULL,
    requests INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    tokens_per_second REAL NOT NULL,
    avg_watts REAL NOT NULL,
    joules_per_token REAL NOT NULL,
    contributor TEXT,
    notes TEXT
);
"""


def gpu_metadata(nvidia_smi_path: str = "nvidia-smi") -> dict[str, Any]:
    try:
        result = subprocess.run(
            [nvidia_smi_path, "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader,nounits"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        rows = [line.split(", ") for line in result.stdout.splitlines() if line.strip()]
        if rows:
            return {
                "gpu_name": rows[0][0],
                "gpu_count": len(rows),
                "driver_version": rows[0][1] if len(rows[0]) > 1 else None,
                "vram_total_mb": float(rows[0][2]) if len(rows[0]) > 2 else None,
            }
    except Exception:
        pass
    return {"gpu_name": None, "gpu_count": None, "driver_version": None, "vram_total_mb": None}


def store_measurement(db_path: str, row: dict[str, Any]) -> None:
    """Append one benchmark row to the public-dataset-shaped SQLite store.

    WAL, cross-thread safe, idempotent on measurement_id.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(MEASUREMENTS_SCHEMA)
        with conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO measurements (
                    measurement_id, ts, gpu_name, gpu_count, driver_version, vram_total_mb,
                    backend, model_name, minutes, requests, output_tokens,
                    tokens_per_second, avg_watts, joules_per_token, contributor, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["measurement_id"],
                    row["ts"],
                    row.get("gpu_name"),
                    row.get("gpu_count"),
                    row.get("driver_version"),
                    row.get("vram_total_mb"),
                    row["backend"],
                    row["model_name"],
                    float(row["minutes"]),
                    int(row["requests"]),
                    int(row["output_tokens"]),
                    float(row["tokens_per_second"]),
                    float(row["avg_watts"]),
                    float(row["joules_per_token"]),
                    row.get("contributor"),
                    row.get("notes"),
                ),
            )
    finally:
        conn.close()


class WattSampler(threading.Thread):
    def __init__(self, telemetry: GPUTelemetry, interval_seconds: float = 5.0):
        super().__init__(daemon=True)
        self.telemetry = telemetry
        self.interval_seconds = interval_seconds
        self.samples: list[float] = []
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.is_set():
            self.samples.append(self.telemetry.total_watts())
            self._stop_event.wait(self.interval_seconds)

    def stop(self) -> float:
        self._stop_event.set()
        self.join(timeout=10)
        return sum(self.samples) / len(self.samples) if self.samples else 0.0


def run_inference_phase(bench_cfg: dict[str, Any], minutes: float, telemetry: GPUTelemetry) -> dict[str, Any]:
    url = str(bench_cfg.get("ollama_url", "http://127.0.0.1:11434")).rstrip("/") + "/api/generate"
    model = str(bench_cfg.get("model", "llama3.1:8b"))
    prompt = str(bench_cfg.get("probe_prompt", "Briefly explain what a hash function does."))
    sampler = WattSampler(telemetry)
    sampler.start()
    deadline = time.monotonic() + minutes * 60
    rates: list[float] = []
    total_output_tokens = 0
    print(f"inference: driving {model} at {url} for {minutes:.1f} minutes...")
    while time.monotonic() < deadline:
        payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
        request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            print(f"inference: request failed ({type(exc).__name__}: {exc}); is Ollama running with the model pulled?")
            break
        eval_count = int(data.get("eval_count", 0))
        eval_duration_ns = int(data.get("eval_duration", 0))
        if eval_duration_ns > 0:
            rates.append(eval_count / (eval_duration_ns / 1e9))
            total_output_tokens += eval_count
    watts = sampler.stop()
    tokens_per_second = sum(rates) / len(rates) if rates else 0.0
    joules_per_token = watts / tokens_per_second if tokens_per_second > 0 else 0.0
    return {
        "model": model,
        "tokens_per_second": round(tokens_per_second, 3),
        "watts": watts,
        "joules_per_token": round(joules_per_token, 6),
        "requests": len(rates),
        "output_tokens": total_output_tokens,
        "measured": bool(rates),
    }


def run_rig_calibration(bench_cfg: dict[str, Any], minutes: float, telemetry: GPUTelemetry) -> dict[str, Any]:
    """Measure this rig's Quai hashrate and watts: the reference_gpu for claim 1."""
    command = [str(part) for part in bench_cfg.get("miner_command", [])]
    if not command:
        print("calibrate-rig: no benchmark.miner_command configured in research.yaml")
        return {"hashrate_hps": 0, "watts": 0.0, "measured": False}
    pattern = re.compile(str(bench_cfg.get("hashrate_regex", r"([0-9]+(?:\.[0-9]+)?)\s*[Mm][Hh]/s")))
    multiplier = int(bench_cfg.get("hashrate_unit_multiplier", 1_000_000))
    readings: list[float] = []

    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def _read_stdout() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            match = pattern.search(line)
            if match:
                readings.append(float(match.group(1)) * multiplier)

    reader = threading.Thread(target=_read_stdout, daemon=True)
    reader.start()
    sampler = WattSampler(telemetry)
    sampler.start()
    print(f"calibrate-rig: running {' '.join(command)} for {minutes:.1f} minutes...")
    time.sleep(minutes * 60)
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
    watts = sampler.stop()
    if not readings:
        print("calibrate-rig: no hashrate lines matched benchmark.hashrate_regex")
        return {"hashrate_hps": 0, "watts": watts, "measured": False}
    hashrate = sum(readings[-20:]) / len(readings[-20:])
    return {"hashrate_hps": int(hashrate), "watts": watts, "measured": True}


def main() -> int:
    parser = argparse.ArgumentParser(description="Claim 3 joules/token measurement and reference-rig calibration")
    parser.add_argument("--config", default="research.yaml")
    parser.add_argument("--minutes", type=float, default=5.0, help="Minutes of measurement")
    parser.add_argument("--calibrate-rig", action="store_true", help="Measure Quai mining hashrate+watts instead of inference")
    parser.add_argument("--store", action="store_true", help="Append the inference measurement to measurements.db (claim 3 dataset)")
    parser.add_argument("--measurements-db", default="measurements.db")
    parser.add_argument("--contributor", default="", help="Handle to credit in the public dataset")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()
    config = load_research_config(args.config)
    bench_cfg = config.get("benchmark", {})
    telemetry = GPUTelemetry(
        nvidia_smi_path=str(bench_cfg.get("nvidia_smi_path", "nvidia-smi")),
        fallback_watts=float(bench_cfg.get("fallback_watts", 300)),
    )

    if args.calibrate_rig:
        rig = run_rig_calibration(bench_cfg, args.minutes, telemetry)
        if rig["measured"]:
            print("\nMeasured reference rig - paste into research.yaml:")
            print("reference_gpu:")
            print(f"  name: \"{gpu_metadata(str(bench_cfg.get('nvidia_smi_path', 'nvidia-smi'))).get('gpu_name') or 'measured-gpu'}\"")
            print(f"  hashrate_hps: {rig['hashrate_hps']}")
            print(f"  watts: {int(round(rig['watts']))}")
        return 0

    inference = run_inference_phase(bench_cfg, args.minutes, telemetry)
    print("\nClaim 3 measurement")
    print(f"  model:            {inference['model']}")
    print(f"  requests:         {inference['requests']}")
    print(f"  tokens/sec:       {inference['tokens_per_second']}")
    print(f"  avg watts:        {inference['watts']:.1f}")
    print(f"  joules/token:     {inference['joules_per_token']}")
    print(f"  boundary:         {MEASUREMENT_BOUNDARY}")
    print("  Qi-denominated index: python3 qi_index.py")
    if args.store:
        if not inference["measured"]:
            print("--store skipped: no successful inference measurement to record")
        else:
            row = {
                "measurement_id": str(uuid4()),
                "ts": datetime.now(timezone.utc).isoformat(),
                **gpu_metadata(str(bench_cfg.get("nvidia_smi_path", "nvidia-smi"))),
                "backend": "ollama",
                "model_name": inference["model"],
                "minutes": args.minutes,
                "requests": inference["requests"],
                "output_tokens": inference["output_tokens"],
                "tokens_per_second": inference["tokens_per_second"],
                "avg_watts": inference["watts"],
                "joules_per_token": inference["joules_per_token"],
                "contributor": args.contributor or None,
                "notes": f"{args.notes + '; ' if args.notes else ''}boundary: {MEASUREMENT_BOUNDARY}",
            }
            store_measurement(args.measurements_db, row)
            print(f"stored measurement {row['measurement_id']} in {args.measurements_db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
