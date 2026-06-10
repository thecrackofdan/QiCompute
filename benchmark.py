"""One-shot crossover benchmark: N minutes mining, N minutes inference, one table.

Run this first on the target rig:

    python3 benchmark.py --minutes 5

Mining phase starts your configured miner and reads live hashrate from its
stdout; inference phase drives local Ollama and measures tokens/sec. Watts are
sampled via nvidia-smi throughout. The table prices both paths per GPU-day
using the same integer money math as the daemon.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import threading
import time
import urllib.request
from typing import Any

from daemon import (
    MICRO,
    fetch_feed,
    inference_gross_usd_micro_per_day,
    load_config,
    micro_to_str,
    mining_gross_usd_micro_per_day,
    parse_difficulty,
    power_cost_usd_micro_per_day,
    to_micro,
)
from telemetry import GPUTelemetry


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


def run_mining_phase(config: dict[str, Any], minutes: float, telemetry: GPUTelemetry) -> dict[str, Any]:
    mining_cfg = config.get("mining", {})
    command = [str(part) for part in mining_cfg.get("miner_command", [])]
    fallback_hashrate = int(mining_cfg.get("fallback_hashrate_hps", 0))
    if not command:
        print("mining: no miner_command configured; using fallback_hashrate_hps from config")
        return {"hashrate_hps": fallback_hashrate, "watts": 0.0, "measured": False}
    pattern = re.compile(str(mining_cfg.get("hashrate_regex", r"([0-9]+(?:\.[0-9]+)?)\s*[Mm][Hh]/s")))
    multiplier = int(mining_cfg.get("hashrate_unit_multiplier", 1_000_000))
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
    print(f"mining: running {' '.join(command)} for {minutes:.1f} minutes...")
    time.sleep(minutes * 60)
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
    watts = sampler.stop()
    hashrate = sum(readings[-20:]) / len(readings[-20:]) if readings else fallback_hashrate
    if not readings:
        print("mining: no hashrate lines matched hashrate_regex; using fallback_hashrate_hps")
    return {"hashrate_hps": int(hashrate), "watts": watts, "measured": bool(readings)}


def run_inference_phase(config: dict[str, Any], minutes: float, telemetry: GPUTelemetry) -> dict[str, Any]:
    inference_cfg = config.get("inference", {})
    url = str(inference_cfg.get("ollama_url", "http://127.0.0.1:11434")).rstrip("/") + "/api/generate"
    model = str(inference_cfg.get("model", "llama3.1:8b"))
    prompt = str(inference_cfg.get("probe_prompt", "Briefly explain what a hash function does."))
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
    return {
        "tokens_per_second": round(tokens_per_second, 3),
        "watts": watts,
        "requests": len(rates),
        "output_tokens": total_output_tokens,
        "measured": bool(rates),
    }


def crossover_table(config: dict[str, Any], mining: dict[str, Any], inference: dict[str, Any]) -> str:
    mining_cfg = config.get("mining", {})
    inference_cfg = config.get("inference", {})
    usd_per_kwh_micro = to_micro(config.get("power", {}).get("usd_per_kwh", "0.12"))

    price_value, price_ok, price_err = fetch_feed(mining_cfg.get("price_feed", {}))
    difficulty_value, difficulty_ok, difficulty_err = fetch_feed(mining_cfg.get("difficulty_feed", {}))
    notes = []
    mining_gross = 0
    if price_ok and difficulty_ok:
        mining_gross = mining_gross_usd_micro_per_day(
            hashrate_hps=int(mining["hashrate_hps"]),
            network_difficulty=parse_difficulty(difficulty_value),
            block_reward_micro_qi=to_micro(mining_cfg.get("block_reward_qi", "0")),
            qi_price_micro_usd=to_micro(price_value),
        )
    else:
        notes.append(f"Quai feeds unavailable (price: {price_err or 'ok'}; difficulty: {difficulty_err or 'ok'}); mining $/day shown as 0 - fix feeds or run the daemon, which defaults to mining on feed errors.")

    rate_value, rate_ok, _ = fetch_feed(inference_cfg.get("market_rate_feed", {}))
    rate_micro = to_micro(rate_value) if rate_ok else to_micro(inference_cfg.get("fallback_usd_per_hour", "0"))
    if not rate_ok:
        notes.append("inference market rate from config fallback_usd_per_hour (no live feed)")
    utilization = int(inference_cfg.get("utilization_percent", 50))
    inference_gross = inference_gross_usd_micro_per_day(
        rate_micro_usd_per_hour=rate_micro, utilization_percent=utilization
    )
    inference_gross_full = inference_gross_usd_micro_per_day(
        rate_micro_usd_per_hour=rate_micro, utilization_percent=100
    )

    mining_power = power_cost_usd_micro_per_day(watts=int(round(mining["watts"])), usd_per_kwh_micro=usd_per_kwh_micro)
    inference_power = power_cost_usd_micro_per_day(watts=int(round(inference["watts"])), usd_per_kwh_micro=usd_per_kwh_micro)
    mining_net = mining_gross - mining_power
    inference_net = inference_gross - inference_power

    lines = [
        "",
        "Crossover Benchmark (per GPU-day)",
        "=" * 64,
        f"{'':28}{'Mining':>16}{'Inference':>16}",
        "-" * 64,
        f"{'hashrate':28}{mining['hashrate_hps'] / 1e6:>13.2f} MH{'-':>16}",
        f"{'tokens/sec':28}{'-':>16}{inference.get('tokens_per_second', 0.0):>16.2f}",
        f"{'avg watts':28}{mining['watts']:>16.1f}{inference['watts']:>16.1f}",
        f"{'gross $/day':28}{micro_to_str(mining_gross):>16}{micro_to_str(inference_gross):>16}",
        f"{'power $/day':28}{micro_to_str(mining_power):>16}{micro_to_str(inference_power):>16}",
        f"{'net $/day':28}{micro_to_str(mining_net):>16}{micro_to_str(inference_net):>16}",
        "-" * 64,
        f"inference at 100% utilization would gross ${micro_to_str(inference_gross_full)}/day "
        f"(table uses {utilization}%)",
        f"verdict: {'INFERENCE' if inference_net > mining_net else 'MINING'} pays more on this rig right now",
    ]
    for note in notes:
        lines.append(f"note: {note}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="One-shot mining vs inference crossover benchmark")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--minutes", type=float, default=5.0, help="Minutes per phase")
    parser.add_argument("--skip-mining", action="store_true")
    parser.add_argument("--skip-inference", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    telemetry = GPUTelemetry(
        nvidia_smi_path=str(config.get("gpu", {}).get("nvidia_smi_path", "nvidia-smi")),
        fallback_watts=float(config.get("power", {}).get("fallback_watts", 300)),
    )
    if args.skip_mining:
        mining = {"hashrate_hps": int(config.get("mining", {}).get("fallback_hashrate_hps", 0)), "watts": 0.0, "measured": False}
    else:
        mining = run_mining_phase(config, args.minutes, telemetry)
    if args.skip_inference:
        inference = {"tokens_per_second": 0.0, "watts": 0.0, "requests": 0, "output_tokens": 0, "measured": False}
    else:
        inference = run_inference_phase(config, args.minutes, telemetry)
    print(crossover_table(config, mining, inference))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
