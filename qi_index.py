"""The live index: Qi cost of 1M tokens today.

Combines claim 1's energy content of Qi (joules per Qi, from current network
difficulty and the reference GPU) with claim 3's measured joules per token.

    python3 qi_index.py
"""
from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from claim1_peg import joules_per_qi
from claim2_stability import latest_measured_joules_per_token
from fetch_data import load_research_config, read_cache


MICRO = 1_000_000


def qi_micro_for_tokens(*, tokens: int, joules_per_token: float, joules_per_qi_value: float) -> int:
    """Integer micro-Qi cost of a token bundle at current energy content."""
    if joules_per_qi_value <= 0:
        return 0
    bundle_joules = Decimal(str(joules_per_token)) * Decimal(int(tokens))
    qi = bundle_joules / Decimal(str(joules_per_qi_value))
    return int(qi * MICRO)


def current_index(config: dict[str, Any], *, sample: bool = False) -> dict[str, Any] | None:
    data_dir = Path("data/sample" if sample else config.get("data_dir", "data"))
    cached = read_cache(data_dir, "difficulty")
    if cached is None or not cached.get("series"):
        return None
    latest_date = max(cached["series"])
    difficulty = float(cached["series"][latest_date])
    gpu = config["reference_gpu"]
    jpq = joules_per_qi(
        difficulty=difficulty,
        block_reward_qi=float(Decimal(str(config["network"]["block_reward_qi"]))),
        hashrate_hps=float(gpu["hashrate_hps"]),
        watts=float(gpu["watts"]),
    )
    jpt = latest_measured_joules_per_token()
    jpt_source = "measurements.db"
    if jpt is None:
        jpt = float(Decimal(str(config["claim2"]["joules_per_token_fallback"])))
        jpt_source = "config fallback (run benchmark.py --store)"
    tokens = int(config["claim2"].get("token_bundle", 1_000_000))
    micro = qi_micro_for_tokens(tokens=tokens, joules_per_token=jpt, joules_per_qi_value=jpq)
    return {
        "as_of": latest_date,
        "difficulty": difficulty,
        "joules_per_qi": round(jpq, 4),
        "joules_per_token": jpt,
        "joules_per_token_source": jpt_source,
        "tokens": tokens,
        "qi_cost_micro": micro,
        "qi_cost": f"{micro // MICRO}.{micro % MICRO:06d}",
        "synthetic": sample,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Qi cost of 1M tokens today")
    parser.add_argument("--config", default="research.yaml")
    parser.add_argument("--sample", action="store_true")
    args = parser.parse_args()
    config = load_research_config(args.config)
    index = current_index(config, sample=args.sample)
    if index is None:
        print("no difficulty cache; run `python3 fetch_data.py` first")
        return 1
    print(json.dumps(index, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
