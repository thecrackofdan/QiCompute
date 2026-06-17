"""Claim 6: workshare-for-inference dual-revenue model.

The core insight: a GPU running the Dominant Strategies InferenceGemm harness
submits Tensor Work Proof (TWP) receipts as native Quai workshares, earning
Qi block rewards *on top of* customer payment. This is not a workaround —
the Quai team has confirmed that TWP inference will be a first-class merge-
mining algorithm alongside SHA-256 (BCH/BTC), Scrypt (LTC/DOGE), and
Ravencoin KawPoW.

This means the GPU IS the miner. There is no time-sharing, no probabilistic
interleaving, no co-located ASIC required. The Tensor Work Receipt from each
inference run is the proof-of-work. The Qi reward is the block subsidy. The
inference fee is the transaction fee. The energy cost is priced in Qi by
construction.

Two revenue streams for an inference node:
  1. Customer payment  — Qi per job, priced at the joule-derived rate (qi_index)
  2. Workshare rewards — Qi per block, proportional to TWP receipts/sec
                         relative to total network TWP difficulty

The dual-revenue break-even is the point where workshare rewards >= energy cost
of running inference, making customer payment pure margin.

Prediction P6 (pre-registered):
  At current network difficulty and a reference RTX 3090 (45 MH/s, 300 W),
  workshare rewards cover >= [5]% of the energy cost of running inference
  continuously. This threshold is intentionally conservative — the claim is
  that the dual-revenue model is economically non-trivial, not that it is
  sufficient alone.

Note: until TWP is live on Quai mainnet, the model uses KawPoW hashrate as
a proxy for TWP receipts/sec. Once the protocol launches, the reference rig
should be calibrated with `benchmark.py --calibrate-rig --algo twp` and the
research.yaml soap.reference_twp block updated accordingly.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from fetch_data import load_research_config, read_cache
from qi_index import MICRO, current_index

# ---------------------------------------------------------------------------
# Core model
# ---------------------------------------------------------------------------

SECONDS_PER_DAY = 86_400
SECONDS_PER_BLOCK = 10  # Quai target block time (seconds)
BLOCKS_PER_DAY = SECONDS_PER_DAY // SECONDS_PER_BLOCK


def expected_workshares_per_day(
    rig_hashrate_mhs: float,
    network_difficulty: float,
    workshare_difficulty_factor: float = 0.1,
) -> float:
    """Expected number of workshares submitted per day by a single rig.

    A workshare meets a lower difficulty threshold than a full block.
    workshare_difficulty_factor is the ratio of workshare threshold to block
    difficulty (default 0.1 = workshares are 10x easier than blocks).

    Expected workshares/day = rig_hashrate / (network_difficulty * factor) * seconds_per_day
    """
    if network_difficulty <= 0 or rig_hashrate_mhs <= 0:
        return 0.0
    rig_hashrate = rig_hashrate_mhs * 1e6  # MH/s -> H/s
    workshare_threshold = network_difficulty * workshare_difficulty_factor
    # Expected time between workshares for this rig (seconds)
    expected_seconds = workshare_threshold / rig_hashrate
    return SECONDS_PER_DAY / expected_seconds


def qi_per_workshare(
    block_reward_qi: float,
    workshares_per_block_target: float = 3.0,
) -> float:
    """Qi earned per workshare submitted.

    Quai's PRS (Proportional Reward Splitting) splits the block reward
    proportionally across workshares included in the block. The soft target
    is 3 workshares per block; each workshare earns block_reward / count.
    """
    if workshares_per_block_target <= 0:
        return 0.0
    return block_reward_qi / workshares_per_block_target


def energy_cost_per_day_qi(
    watts: float,
    joules_per_qi: float,
) -> float:
    """Energy cost of running the rig for one day, denominated in Qi.

    joules_per_qi comes from the Qi index (claim 1 difficulty -> energy model).
    """
    joules_per_day = watts * SECONDS_PER_DAY
    return joules_per_day / joules_per_qi if joules_per_qi > 0 else float("inf")


def workshare_coverage_fraction(
    workshare_qi_per_day: float,
    energy_cost_qi_per_day: float,
) -> float:
    """Fraction of energy cost covered by workshare rewards alone."""
    if energy_cost_qi_per_day <= 0:
        return 0.0
    return workshare_qi_per_day / energy_cost_qi_per_day


def dual_revenue_model(
    config: dict[str, Any],
    index: dict[str, Any],
    difficulty: float,
) -> dict[str, Any]:
    """Compute the full dual-revenue model for the reference rig."""
    ref = config.get("reference_gpu", {})
    rig_hashrate_mhs = float(ref.get("hashrate_mhs", 45.0))
    rig_watts = float(ref.get("watts", 300.0))
    rig_name = ref.get("name", "RTX 3090 (default)")

    claim6_cfg = config.get("claim6", {})
    workshare_difficulty_factor = float(
        claim6_cfg.get("workshare_difficulty_factor", 0.1)
    )
    block_reward_qi = float(claim6_cfg.get("block_reward_qi", 1.0))
    workshares_per_block_target = float(
        claim6_cfg.get("workshares_per_block_target", 3.0)
    )
    coverage_threshold = float(claim6_cfg.get("coverage_threshold_fraction", 0.05))

    joules_per_qi = index["joules_per_qi"]
    joules_per_token = index["joules_per_token"]
    tokens_per_million = 1_000_000

    # Workshare revenue
    ws_per_day = expected_workshares_per_day(
        rig_hashrate_mhs, difficulty, workshare_difficulty_factor
    )
    qi_per_ws = qi_per_workshare(block_reward_qi, workshares_per_block_target)
    workshare_qi_per_day = ws_per_day * qi_per_ws

    # Energy cost
    energy_qi_per_day = energy_cost_per_day_qi(rig_watts, joules_per_qi)

    # Customer revenue (at full capacity, continuous inference)
    # tokens/sec from benchmark; fallback to config
    tokens_per_sec = float(claim6_cfg.get("tokens_per_sec_fallback", 50.0))
    tokens_per_day = tokens_per_sec * SECONDS_PER_DAY
    customer_qi_per_day = (
        tokens_per_day / tokens_per_million
    ) * (index["qi_cost_micro"] / MICRO)

    # Coverage
    coverage = workshare_coverage_fraction(workshare_qi_per_day, energy_qi_per_day)

    # Break-even: how many tokens/day needed so customer revenue covers remaining energy
    remaining_energy_qi = max(0.0, energy_qi_per_day - workshare_qi_per_day)
    qi_per_million_tokens = index["qi_cost_micro"] / MICRO
    breakeven_tokens_per_day = (
        (remaining_energy_qi / qi_per_million_tokens) * tokens_per_million
        if qi_per_million_tokens > 0
        else float("inf")
    )
    breakeven_utilisation = (
        breakeven_tokens_per_day / tokens_per_day if tokens_per_day > 0 else float("inf")
    )

    # Verdict
    if coverage >= coverage_threshold:
        verdict = "dual_revenue_non_trivial"
        verdict_reason = (
            f"workshare rewards cover {coverage:.1%} of energy cost "
            f"(threshold: {coverage_threshold:.0%}); "
            f"break-even utilisation: {min(breakeven_utilisation, 1.0):.1%}"
        )
    else:
        verdict = "dual_revenue_below_threshold"
        verdict_reason = (
            f"workshare rewards cover only {coverage:.1%} of energy cost "
            f"(threshold: {coverage_threshold:.0%}); "
            f"network difficulty may be too high for this rig class"
        )

    return {
        "rig_name": rig_name,
        "rig_hashrate_mhs": rig_hashrate_mhs,
        "rig_watts": rig_watts,
        "difficulty": difficulty,
        "joules_per_qi": joules_per_qi,
        "workshare_difficulty_factor": workshare_difficulty_factor,
        "block_reward_qi": block_reward_qi,
        "workshares_per_block_target": workshares_per_block_target,
        # Workshare stream
        "expected_workshares_per_day": round(ws_per_day, 2),
        "qi_per_workshare": round(qi_per_ws, 6),
        "workshare_qi_per_day": round(workshare_qi_per_day, 4),
        # Energy cost
        "energy_cost_qi_per_day": round(energy_qi_per_day, 4),
        # Customer stream (at full capacity)
        "tokens_per_sec": tokens_per_sec,
        "tokens_per_day": round(tokens_per_day),
        "customer_qi_per_day_at_full_capacity": round(customer_qi_per_day, 4),
        # Combined
        "total_qi_per_day_at_full_capacity": round(
            workshare_qi_per_day + customer_qi_per_day, 4
        ),
        "workshare_coverage_fraction": round(coverage, 6),
        "breakeven_utilisation_fraction": round(min(breakeven_utilisation, 1.0), 4),
        "coverage_threshold": coverage_threshold,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
    }


# ---------------------------------------------------------------------------
# Sensitivity table
# ---------------------------------------------------------------------------

# Bitcoin network hashrate reference (approximate, as of 2025-2026)
# 800 EH/s = 800e18 H/s = 800_000_000_000 MH/s
BITCOIN_HASHRATE_EHS = 800.0  # EH/s
BITCOIN_HASHRATE_MHS = BITCOIN_HASHRATE_EHS * 1e12  # EH/s -> MH/s

# SOAP adoption scenarios: fraction of Bitcoin's SHA-256 hashrate
# pointing workshares at Quai
SOAP_ADOPTION_SCENARIOS = [
    ("0.01%", 0.0001),
    ("0.1%",  0.001),
    ("1%",    0.01),
    ("5%",    0.05),
    ("10%",   0.10),
]


def sensitivity_table(
    config: dict[str, Any],
    index: dict[str, Any],
    difficulty: float,
) -> list[dict[str, Any]]:
    """Coverage fraction across a range of hashrates and difficulty multipliers."""
    ref = config.get("reference_gpu", {})
    base_hashrate = float(ref.get("hashrate_mhs", 45.0))
    base_watts = float(ref.get("watts", 300.0))
    claim6_cfg = config.get("claim6", {})
    workshare_difficulty_factor = float(claim6_cfg.get("workshare_difficulty_factor", 0.1))
    block_reward_qi = float(claim6_cfg.get("block_reward_qi", 1.0))
    workshares_per_block_target = float(claim6_cfg.get("workshares_per_block_target", 3.0))
    joules_per_qi = index["joules_per_qi"]

    rows = []
    for hashrate_mult in (0.25, 0.5, 1.0, 2.0, 4.0):
        for diff_mult in (0.1, 0.5, 1.0, 2.0, 5.0):
            hr = base_hashrate * hashrate_mult
            diff = difficulty * diff_mult
            ws_day = expected_workshares_per_day(hr, diff, workshare_difficulty_factor)
            qi_ws = qi_per_workshare(block_reward_qi, workshares_per_block_target)
            ws_qi = ws_day * qi_ws
            # scale watts proportionally to hashrate (rough linear approximation)
            watts = base_watts * hashrate_mult
            e_qi = energy_cost_per_day_qi(watts, joules_per_qi)
            cov = workshare_coverage_fraction(ws_qi, e_qi)
            rows.append({
                "hashrate_mhs": round(hr, 1),
                "difficulty_multiplier": diff_mult,
                "workshare_qi_per_day": round(ws_qi, 4),
                "energy_cost_qi_per_day": round(e_qi, 4),
                "coverage_fraction": round(cov, 4),
                "scenario": "gpu_rig",
            })
    return rows


def bitcoin_soap_scenarios(
    config: dict[str, Any],
    index: dict[str, Any],
    difficulty: float,
) -> list[dict[str, Any]]:
    """Model the dual-revenue economics at Bitcoin-scale SHA-256 SOAP adoption.

    Each row represents a fraction of Bitcoin's total SHA-256 hashrate
    submitting workshares to Quai. The GPU inference node is separate
    (ASIC + GPU split: ASIC handles workshares, GPU handles inference).
    The GPU energy cost is fixed at the reference rig; the ASIC workshare
    revenue scales with the adopted hashrate fraction.

    This is the cleanest version of the dual-revenue model: no GPU time-sharing,
    no probabilistic interleaving. The ASIC mines BTC/BCH and submits Quai
    workshares; the GPU serves inference uninterrupted.
    """
    ref = config.get("reference_gpu", {})
    rig_watts = float(ref.get("watts", 300.0))
    claim6_cfg = config.get("claim6", {})
    workshare_difficulty_factor = float(claim6_cfg.get("workshare_difficulty_factor", 0.1))
    block_reward_qi = float(claim6_cfg.get("block_reward_qi", 1.0))
    workshares_per_block_target = float(claim6_cfg.get("workshares_per_block_target", 3.0))
    joules_per_qi = index["joules_per_qi"]

    # GPU inference energy cost (fixed — ASIC handles workshares separately)
    gpu_energy_qi_per_day = energy_cost_per_day_qi(rig_watts, joules_per_qi)

    rows = []
    for label, fraction in SOAP_ADOPTION_SCENARIOS:
        adopted_hashrate_mhs = BITCOIN_HASHRATE_MHS * fraction
        ws_day = expected_workshares_per_day(
            adopted_hashrate_mhs, difficulty, workshare_difficulty_factor
        )
        qi_ws = qi_per_workshare(block_reward_qi, workshares_per_block_target)
        ws_qi_per_day = ws_day * qi_ws
        # Coverage: ASIC workshare revenue vs GPU inference energy cost
        cov = workshare_coverage_fraction(ws_qi_per_day, gpu_energy_qi_per_day)
        rows.append({
            "btc_hashrate_fraction": label,
            "adopted_hashrate_ehs": round(BITCOIN_HASHRATE_EHS * fraction, 4),
            "workshare_qi_per_day": round(ws_qi_per_day, 2),
            "gpu_energy_cost_qi_per_day": round(gpu_energy_qi_per_day, 4),
            "coverage_fraction": round(cov, 4),
        })
    return rows


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def render_markdown(
    result: dict[str, Any],
    sensitivity: list[dict[str, Any]],
    *,
    synthetic: bool,
    btc_scenarios: list[dict[str, Any]] | None = None,
) -> str:
    lines: list[str] = []
    if synthetic:
        lines.append(
            "> **SYNTHETIC SAMPLE DATA** - pipeline demonstration only, not a finding.\n"
        )
    lines.append("# Claim 6: Workshare-for-Inference Dual-Revenue Model\n")
    lines.append(
        "A GPU running the InferenceGemm harness submits **Tensor Work Proof (TWP) receipts "
        "as native Quai workshares**, earning Qi block rewards on top of customer payment. "
        "TWP inference is a confirmed first-class merge-mining algorithm on Quai alongside "
        "SHA-256 (BCH/BTC), Scrypt (LTC/DOGE), and Ravencoin KawPoW. "
        "The GPU IS the miner: the TWP receipt is the proof-of-work, the Qi reward is the "
        "block subsidy, and the inference fee is the transaction fee.\n"
    )
    lines.append(f"**Reference rig:** {result['rig_name']} "
                 f"({result['rig_hashrate_mhs']} MH/s, {result['rig_watts']} W)\n")

    lines.append("## Revenue streams\n")
    lines.append("| Stream | Qi/day |")
    lines.append("| --- | --- |")
    lines.append(f"| Workshare rewards ({result['expected_workshares_per_day']:.1f} workshares/day × {result['qi_per_workshare']:.6f} Qi/workshare) | **{result['workshare_qi_per_day']:.4f}** |")
    lines.append(f"| Customer payment (full capacity: {result['tokens_per_day']:,.0f} tokens/day) | {result['customer_qi_per_day_at_full_capacity']:.4f} |")
    lines.append(f"| Energy cost | -{result['energy_cost_qi_per_day']:.4f} |")
    lines.append(f"| **Net at full capacity** | **{result['total_qi_per_day_at_full_capacity'] - result['energy_cost_qi_per_day']:.4f}** |\n")

    lines.append("## Key metrics\n")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| Workshare energy coverage | **{result['workshare_coverage_fraction']:.1%}** (threshold: {result['coverage_threshold']:.0%}) |")
    lines.append(f"| Break-even utilisation | {result['breakeven_utilisation_fraction']:.1%} of capacity |")
    lines.append(f"| Network difficulty | {result['difficulty']:.3e} |")
    lines.append(f"| Joules per Qi | {result['joules_per_qi']:.0f} J/Qi |\n")

    lines.append(f"## Verdict: `{result['verdict']}`\n")
    lines.append(f"{result['verdict_reason']}\n")

    lines.append("## Sensitivity: workshare coverage across hashrates and difficulty\n")
    lines.append("| Hashrate (MH/s) | Difficulty multiplier | Workshare Qi/day | Energy cost Qi/day | Coverage |")
    lines.append("| --- | --- | --- | --- | --- |")
    for row in sensitivity:
        lines.append(
            f"| {row['hashrate_mhs']} | {row['difficulty_multiplier']}x | "
            f"{row['workshare_qi_per_day']} | {row['energy_cost_qi_per_day']} | "
            f"{row['coverage_fraction']:.1%} |"
        )
    lines.append("")

    # Bitcoin-scale SOAP adoption scenarios
    if btc_scenarios:
        lines.append(
            "## Bitcoin-scale SOAP adoption: ASIC workshares + GPU inference\n"
        )
        lines.append(
            "The cleanest dual-revenue model: a SHA-256 ASIC mines BTC/BCH and submits "
            "Quai workshares via Project SOAP; a co-located GPU serves inference "
            "uninterrupted. No GPU time-sharing required. The table shows workshare "
            f"revenue vs GPU inference energy cost ({result['rig_watts']} W reference) "
            f"at each fraction of Bitcoin's ~{BITCOIN_HASHRATE_EHS:.0f} EH/s hashrate.\n"
        )
        lines.append(
            "| BTC hashrate fraction | Adopted hashrate (EH/s) | Workshare Qi/day "
            "| GPU energy cost Qi/day | ASIC coverage of GPU energy |"
        )
        lines.append("| --- | --- | --- | --- | --- |")
        for row in btc_scenarios:
            lines.append(
                f"| {row['btc_hashrate_fraction']} "
                f"| {row['adopted_hashrate_ehs']:.4f} "
                f"| {row['workshare_qi_per_day']:,.2f} "
                f"| {row['gpu_energy_cost_qi_per_day']:.4f} "
                f"| {row['coverage_fraction']:.1%} |"
            )
        lines.append("")
        lines.append(
            "> **Interpretation:** at 1% of Bitcoin's hashrate pointing workshares at Quai, "
            "the ASIC workshare revenue dwarfs the GPU inference energy cost — the GPU "
            "effectively runs inference for free from an energy perspective. This is not a "
            "prediction that 1% of Bitcoin's hashrate will adopt SOAP; it is a model of "
            "what the economics look like *if* they do. Claim 7 tracks the actual SOAP "
            "adoption rate as a leading indicator of energy anchor strength.\n"
        )

    lines.append(
        "> **Note on workshare difficulty factor:** the default factor of "
        f"{result['workshare_difficulty_factor']} (workshares are "
        f"{1/result['workshare_difficulty_factor']:.0f}x easier than full blocks) "
        "is a protocol-level parameter. The actual factor is configurable in "
        "`research.yaml` → `claim6.workshare_difficulty_factor` and should be "
        "calibrated against observed workshare inclusion rates once real data is available.\n"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Claim 6: workshare-for-inference dual-revenue model"
    )
    parser.add_argument("--config", default="research.yaml")
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Use synthetic sample fixtures (testing only)",
    )
    args = parser.parse_args()

    config = load_research_config(args.config)
    data_dir = Path("data/sample" if args.sample else config.get("data_dir", "data"))

    # Load difficulty (required)
    diff_cache = read_cache(data_dir, "difficulty")
    if diff_cache is None:
        print("missing difficulty cache - run `python3 fetch_data.py` first")
        return 1
    # Use the latest difficulty value
    difficulty_series = {
        date: float(v) for date, v in diff_cache["series"].items()
    }
    latest_difficulty = difficulty_series[max(difficulty_series)]

    # Load Qi index
    index = current_index(config, sample=args.sample)
    if index is None:
        print("missing difficulty cache for qi_index - run `python3 fetch_data.py` first")
        return 1

    result = dual_revenue_model(config, index, latest_difficulty)
    sensitivity = sensitivity_table(config, index, latest_difficulty)
    btc_scenarios = bitcoin_soap_scenarios(config, index, latest_difficulty)

    results_dir = Path(config.get("results_dir", "results"))
    results_dir.mkdir(parents=True, exist_ok=True)

    # Save JSON stats
    stats = {k: v for k, v in result.items()}
    stats["synthetic"] = args.sample
    stats["btc_soap_scenarios"] = btc_scenarios
    (results_dir / "claim6_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf-8"
    )

    markdown = render_markdown(
        result, sensitivity, synthetic=args.sample, btc_scenarios=btc_scenarios
    )
    (results_dir / "claim6.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"claim6: written to results/claim6.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
