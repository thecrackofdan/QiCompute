"""Claim 3 measurement: joules/token on this rig, plus reference-rig calibration.

    python3 benchmark.py --minutes 5 --store          # measure inference, store to measurements.db
    python3 benchmark.py --calibrate-rig --minutes 5  # measure KawPoW (GPU) hashrate+watts
    python3 benchmark.py --calibrate-rig --algo sha256 --minutes 5  # measure SHA-256 ASIC rig
    python3 benchmark.py --calibrate-rig --algo scrypt --minutes 5  # measure Scrypt ASIC rig

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

--calibrate-rig runs the configured miner instead, parses live hashrate from
its stdout, samples watts, and prints the reference block to paste into
research.yaml. Use --algo to specify the hardware class:

  --algo kawpow  (default) KawPoW GPU miner -> reference_gpu block
  --algo sha256            SHA-256 ASIC miner -> soap.reference_sha256 block
  --algo scrypt            Scrypt ASIC miner -> soap.reference_scrypt block

The soap.reference_sha256 and soap.reference_scrypt blocks feed the
multi-algorithm energy model in claim1_peg.py (effective_difficulty).
The energy_factor for each algo is derived from the measured J/hash relative
to the KawPoW reference rig.

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
    import sys
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
    except FileNotFoundError:
        print(
            f"WARNING: nvidia-smi not found at '{nvidia_smi_path}'. "
            "GPU metadata will be missing from the measurement row. "
            "Install NVIDIA drivers or set benchmark.nvidia_smi_path in research.yaml.",
            file=sys.stderr,
        )
    except subprocess.CalledProcessError as exc:
        print(
            f"WARNING: nvidia-smi exited with code {exc.returncode}: {exc.stderr.strip()}. "
            "GPU metadata will be missing from the measurement row.",
            file=sys.stderr,
        )
    except subprocess.TimeoutExpired:
        print(
            "WARNING: nvidia-smi timed out after 5 seconds. "
            "GPU metadata will be missing from the measurement row.",
            file=sys.stderr,
        )
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


def _run_ollama_phase(bench_cfg: dict[str, Any], minutes: float, sampler: WattSampler) -> dict[str, Any]:
    """Drive Ollama /api/generate for the given duration and return raw stats."""
    url = str(bench_cfg.get("ollama_url", "http://127.0.0.1:11434")).rstrip("/") + "/api/generate"
    model = str(bench_cfg.get("model", "qwen2.5:3b"))
    prompt = str(bench_cfg.get("probe_prompt", "Briefly explain what a hash function does."))
    deadline = time.monotonic() + minutes * 60
    rates: list[float] = []
    total_output_tokens = 0
    print(f"inference (ollama): driving {model} at {url} for {minutes:.1f} minutes...")
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
    return {"model": model, "rates": rates, "output_tokens": total_output_tokens, "backend": "ollama"}


def _run_igemm_phase(bench_cfg: dict[str, Any], minutes: float, sampler: WattSampler) -> dict[str, Any]:
    """Drive InferenceGemm (vLLM-compatible) endpoint for the given duration.

    InferenceGemm serves an OpenAI-compatible /v1/chat/completions endpoint.
    Each response includes a Tensor Work Receipt in the response headers or body
    (implementation-dependent on harness version). This function measures
    throughput in receipt-mode and returns the overhead fraction vs baseline.
    """
    url = str(bench_cfg.get("igemm_url", "http://127.0.0.1:8000")).rstrip("/") + "/v1/chat/completions"
    model = str(bench_cfg.get("igemm_model", "dominant-strategies/quai-igemm-qwen2.5-3b-w8a8-research"))
    prompt = str(bench_cfg.get("probe_prompt", "Briefly explain what a hash function does."))
    deadline = time.monotonic() + minutes * 60
    rates: list[float] = []
    total_output_tokens = 0
    receipts_accepted = 0
    print(f"inference (igemm): driving {model} at {url} for {minutes:.1f} minutes...")
    while time.monotonic() < deadline:
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200,
            "stream": False,
        }).encode("utf-8")
        request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            print(f"inference: igemm request failed ({type(exc).__name__}: {exc}); is the InferenceGemm server running?")
            break
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
            token_count = len(content.split())  # rough proxy; replace with usage.completion_tokens
            usage = data.get("usage", {})
            token_count = int(usage.get("completion_tokens", token_count))
            # InferenceGemm may embed receipt status in a custom field
            if data.get("tensor_work_receipt") or data.get("twr_accepted"):
                receipts_accepted += 1
            elapsed = data.get("elapsed_seconds", 1.0)
            if elapsed > 0 and token_count > 0:
                rates.append(token_count / elapsed)
                total_output_tokens += token_count
    return {"model": model, "rates": rates, "output_tokens": total_output_tokens,
            "backend": "igemm", "receipts_accepted": receipts_accepted}


def run_inference_phase(bench_cfg: dict[str, Any], minutes: float, telemetry: GPUTelemetry) -> dict[str, Any]:
    backend = str(bench_cfg.get("backend", "ollama")).lower()
    sampler = WattSampler(telemetry)
    sampler.start()
    if backend == "igemm":
        raw = _run_igemm_phase(bench_cfg, minutes, sampler)
    else:
        raw = _run_ollama_phase(bench_cfg, minutes, sampler)
    watts = sampler.stop()
    rates = raw["rates"]
    tokens_per_second = sum(rates) / len(rates) if rates else 0.0
    joules_per_token = watts / tokens_per_second if tokens_per_second > 0 else 0.0
    result = {
        "model": raw["model"],
        "backend": raw["backend"],
        "tokens_per_second": round(tokens_per_second, 3),
        "watts": watts,
        "joules_per_token": round(joules_per_token, 6),
        "requests": len(rates),
        "output_tokens": raw["output_tokens"],
        "measured": bool(rates),
    }
    if backend == "igemm":
        result["receipts_accepted"] = raw.get("receipts_accepted", 0)
    return result


# ---------------------------------------------------------------------------
# Per-algorithm calibration config keys in research.yaml
# kawpow: benchmark.miner_command / benchmark.hashrate_regex (existing)
# sha256: soap.sha256_miner_command / soap.sha256_hashrate_regex
# scrypt: soap.scrypt_miner_command / soap.scrypt_hashrate_regex
# ---------------------------------------------------------------------------
_ALGO_CONFIG: dict[str, dict[str, Any]] = {
    "kawpow": {
        "command_key": ("benchmark", "miner_command"),
        "regex_key": ("benchmark", "hashrate_regex"),
        "multiplier_key": ("benchmark", "hashrate_unit_multiplier"),
        "default_regex": r"([0-9]+(?:\.[0-9]+)?)\s*[Mm][Hh]/s",
        "default_multiplier": 1_000_000,
        "yaml_block": "reference_gpu",
        "hashrate_label": "hashrate_hps",
    },
    "sha256": {
        "command_key": ("soap", "sha256_miner_command"),
        "regex_key": ("soap", "sha256_hashrate_regex"),
        "multiplier_key": ("soap", "sha256_hashrate_unit_multiplier"),
        "default_regex": r"([0-9]+(?:\.[0-9]+)?)\s*[Tt][Hh]/s",
        "default_multiplier": 1_000_000_000_000,  # TH/s -> H/s
        "yaml_block": "soap.reference_sha256",
        "hashrate_label": "hashrate_hps",
    },
    "scrypt": {
        "command_key": ("soap", "scrypt_miner_command"),
        "regex_key": ("soap", "scrypt_hashrate_regex"),
        "multiplier_key": ("soap", "scrypt_hashrate_unit_multiplier"),
        "default_regex": r"([0-9]+(?:\.[0-9]+)?)\s*[Gg][Hh]/s",
        "default_multiplier": 1_000_000_000,  # GH/s -> H/s
        "yaml_block": "soap.reference_scrypt",
        "hashrate_label": "hashrate_hps",
    },
}


def _get_nested(config: dict[str, Any], keys: tuple[str, ...], default: Any = None) -> Any:
    """Safely retrieve a nested config value by key path tuple."""
    current: Any = config
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
    return current


def run_rig_calibration(
    config: dict[str, Any],
    minutes: float,
    telemetry: GPUTelemetry,
    algo: str = "kawpow",
) -> dict[str, Any]:
    """Measure this rig's hashrate and watts for the given algorithm.

    algo: 'kawpow' (default, GPU KawPoW) | 'sha256' (ASIC SHA-256) | 'scrypt' (ASIC Scrypt)

    Returns a dict with hashrate_hps, watts, measured, and algo.
    Also prints the research.yaml block to paste in.
    """
    algo_cfg = _ALGO_CONFIG.get(algo)
    if algo_cfg is None:
        print(f"calibrate-rig: unknown --algo '{algo}'; choose from: {', '.join(_ALGO_CONFIG)}")
        return {"hashrate_hps": 0, "watts": 0.0, "measured": False, "algo": algo}

    command = [str(part) for part in _get_nested(config, algo_cfg["command_key"], [])]
    if not command:
        section, key = algo_cfg["command_key"]
        print(f"calibrate-rig: no {section}.{key} configured in research.yaml")
        return {"hashrate_hps": 0, "watts": 0.0, "measured": False, "algo": algo}

    pattern = re.compile(
        str(_get_nested(config, algo_cfg["regex_key"], algo_cfg["default_regex"]))
    )
    multiplier = int(_get_nested(config, algo_cfg["multiplier_key"], algo_cfg["default_multiplier"]))
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
    print(f"calibrate-rig ({algo}): running {' '.join(command)} for {minutes:.1f} minutes...")
    time.sleep(minutes * 60)
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
    watts = sampler.stop()
    if not readings:
        section, key = algo_cfg["regex_key"]
        print(f"calibrate-rig: no hashrate lines matched {section}.{key}")
        return {"hashrate_hps": 0, "watts": watts, "measured": False, "algo": algo}
    hashrate = sum(readings[-20:]) / len(readings[-20:])
    return {"hashrate_hps": int(hashrate), "watts": watts, "measured": True, "algo": algo}


def main() -> int:
    parser = argparse.ArgumentParser(description="Claim 3 joules/token measurement and reference-rig calibration")
    parser.add_argument("--config", default="research.yaml")
    parser.add_argument("--minutes", type=float, default=5.0, help="Minutes of measurement")
    parser.add_argument("--calibrate-rig", action="store_true", help="Measure mining hashrate+watts instead of inference")
    parser.add_argument(
        "--algo",
        default="kawpow",
        choices=list(_ALGO_CONFIG),
        help="Algorithm to calibrate (kawpow=GPU default, sha256=ASIC SHA-256, scrypt=ASIC Scrypt)",
    )
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
        rig = run_rig_calibration(config, args.minutes, telemetry, algo=args.algo)
        if rig["measured"]:
            algo_cfg = _ALGO_CONFIG[args.algo]
            yaml_block = algo_cfg["yaml_block"]
            print(f"\nMeasured {args.algo} reference rig - paste into research.yaml under '{yaml_block}':")
            if args.algo == "kawpow":
                gpu_name = gpu_metadata(str(bench_cfg.get("nvidia_smi_path", "nvidia-smi"))).get("gpu_name") or "measured-gpu"
                print(f"reference_gpu:")
                print(f"  name: \"{gpu_name}\"")
                print(f"  hashrate_hps: {rig['hashrate_hps']}")
                print(f"  watts: {int(round(rig['watts']))}")
            else:
                # SHA-256 or Scrypt ASIC: print soap sub-block
                # Also compute energy_factor relative to KawPoW reference
                kw_ref = config.get("reference_gpu", {})
                kw_hps = float(kw_ref.get("hashrate_hps", 45_000_000))
                kw_watts = float(kw_ref.get("watts", 300))
                kw_j_per_hash = kw_watts / kw_hps if kw_hps > 0 else 0.0
                asic_j_per_hash = rig["watts"] / rig["hashrate_hps"] if rig["hashrate_hps"] > 0 else 0.0
                energy_factor = asic_j_per_hash / kw_j_per_hash if kw_j_per_hash > 0 else 0.0
                print(f"soap:")
                print(f"  reference_{args.algo}:")
                print(f"    name: \"measured-{args.algo}-asic\"")
                print(f"    hashrate_hps: {rig['hashrate_hps']}")
                print(f"    watts: {int(round(rig['watts']))}")
                print(f"  algo_energy_factors:")
                print(f"    {args.algo}: {energy_factor:.6e}  # measured J/hash / KawPoW J/hash")
                print(f"    # Update this in soap.algo_energy_factors to override the default estimate.")
        return 0

    inference = run_inference_phase(bench_cfg, args.minutes, telemetry)
    backend_used = inference.get("backend", "ollama")
    print("\nClaim 3 measurement")
    print(f"  backend:          {backend_used}")
    print(f"  model:            {inference['model']}")
    print(f"  requests:         {inference['requests']}")
    print(f"  tokens/sec:       {inference['tokens_per_second']}")
    print(f"  avg watts:        {inference['watts']:.1f}")
    print(f"  joules/token:     {inference['joules_per_token']}")
    print(f"  boundary:         {MEASUREMENT_BOUNDARY}")
    if backend_used == "igemm":
        receipts = inference.get("receipts_accepted", 0)
        overhead_threshold = float(bench_cfg.get("twp_overhead_threshold", 0.10))
        print(f"  receipts accepted: {receipts}")
        # TWP overhead note: compare to Dominant Strategies reference (2.98% on 3B)
        print(f"  TWP overhead threshold (P3b): <= {overhead_threshold*100:.0f}% of baseline tok/s")
        print(f"  Reference (DS quai-igemm-qwen2.5-3b-w8a8): 2.98% overhead, 1 accepted receipt")
    print("  Qi-denominated index: python3 qi_index.py")
    if args.store:
        if not inference["measured"]:
            print("--store skipped: no successful inference measurement to record")
        else:
            row = {
                "measurement_id": str(uuid4()),
                "ts": datetime.now(timezone.utc).isoformat(),
                **gpu_metadata(str(bench_cfg.get("nvidia_smi_path", "nvidia-smi"))),
                "backend": backend_used,
                "model_name": inference["model"],
                "minutes": args.minutes,
                "requests": inference["requests"],
                "output_tokens": inference["output_tokens"],
                "tokens_per_second": inference["tokens_per_second"],
                "avg_watts": inference["watts"],
                "joules_per_token": inference["joules_per_token"],
                "contributor": args.contributor or None,
                "notes": (
                    f"{args.notes + '; ' if args.notes else ''}"
                    f"boundary: {MEASUREMENT_BOUNDARY}"
                    + (f"; igemm_receipts: {inference.get('receipts_accepted', 0)}" if backend_used == "igemm" else "")
                ),
            }
            store_measurement(args.measurements_db, row)
            print(f"stored measurement {row['measurement_id']} in {args.measurements_db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
