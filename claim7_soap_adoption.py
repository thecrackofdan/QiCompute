"""Claim 7: SOAP adoption rate as a leading indicator of energy anchor strength.

Project SOAP (Subsidized Open-market Acquisition Protocol, launched Dec 2025)
allows SHA-256 ASICs (Bitcoin Cash/Bitcoin hardware), Scrypt ASICs
(Litecoin/Dogecoin hardware), and Ravencoin KawPoW GPUs to submit workshares
to Quai blocks and earn QUAI rewards. The parent chain block reward goes to a
protocol-controlled buyback address; the miner earns QUAI for the same work.

The Quai team has also confirmed that Tensor Work Proof (TWP) inference will
be added as a first-class merge-mining algorithm. This means GPU inference
workers (running InferenceGemm) will submit TWP receipts as native workshares
and earn Qi rewards — making the GPU both a miner and an inference provider
without any time-sharing or co-located ASIC required.

The thesis: if the combined SOAP+TWP workshare fraction of Quai's effective
difficulty grows over time, it is direct on-chain evidence that:
  1. The energy anchor is broadening — more diverse, geographically distributed
     hardware (ASICs, inference GPUs) is contributing to Qi's energy backing.
  2. The merge-mining flywheel is active — miners are finding it profitable
     to point at Quai, which means the QUAI/Qi reward is non-trivial relative
     to their primary chain reward.
  3. The dual-revenue model (Claim 6) is becoming more accessible — as SOAP
     and TWP adoption grows, the standard inference node IS a Quai miner.

Prediction P7 (pre-registered):
  The SOAP workshare fraction of total effective difficulty grows monotonically
  over any 90-day window after SOAP launch (Dec 2025), with a minimum growth
  rate of [1 percentage point per quarter] from baseline. TWP workshare
  fraction is tracked separately once the protocol launches.

This claim does NOT assert that Bitcoin's hashrate will flow to Quai. It tests
whether the SOAP/TWP mechanism is attracting any meaningful participation at
all, and tracks the growth rate as a leading indicator of energy anchor
broadening.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from fetch_data import load_research_config, read_cache
from series import align_by_date, log_returns, ols


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

SOAP_LAUNCH_DATE = "2025-12-01"  # approximate SOAP mainnet launch


def soap_fraction_series(
    kawpow_ws: dict[str, float],
    soap_ws: dict[str, float],
    block_difficulty: dict[str, float],
) -> dict[str, float]:
    """Compute the daily SOAP workshare fraction of total effective difficulty.

    SOAP fraction = soap_ws_difficulty / (block_difficulty + kawpow_ws + soap_ws)

    Returns a dict of {date: fraction} for dates where all three series overlap.
    """
    dates, (kw, sw, bd) = align_by_date(kawpow_ws, soap_ws, block_difficulty)
    result = {}
    for i, date in enumerate(dates):
        total = bd[i] + kw[i] + sw[i]
        result[date] = sw[i] / total if total > 0 else 0.0
    return result


def growth_rate_analysis(
    fraction_series: dict[str, float],
    min_samples: int = 90,
) -> dict[str, Any]:
    """Analyse the growth rate of the SOAP fraction series.

    Returns OLS slope (fraction/day), annualised growth rate, and verdict.
    """
    if len(fraction_series) < min_samples:
        return {
            "verdict": "insufficient_data",
            "verdict_reason": (
                f"only {len(fraction_series)} days of data; "
                f"need >= {min_samples} for a reliable trend"
            ),
            "n_days": len(fraction_series),
            "min_samples": min_samples,
        }

    dates = sorted(fraction_series)
    fractions = [fraction_series[d] for d in dates]

    # Day index as x (0, 1, 2, ...)
    xs = [float(i) for i in range(len(dates))]
    fit = ols(xs, fractions)

    slope_per_day = fit["beta"]  # fraction/day
    slope_per_quarter = slope_per_day * 90  # fraction/quarter (90 days)
    slope_pct_per_quarter = slope_per_quarter * 100  # percentage points/quarter

    # Latest fraction
    latest_fraction = fractions[-1]
    baseline_fraction = fractions[0]

    return {
        "n_days": len(dates),
        "date_start": dates[0],
        "date_end": dates[-1],
        "baseline_fraction": round(baseline_fraction, 6),
        "latest_fraction": round(latest_fraction, 6),
        "slope_per_day": round(slope_per_day, 8),
        "slope_pct_per_quarter": round(slope_pct_per_quarter, 4),
        "r_squared": round(fit["r_squared"], 4),
        "fit_alpha": round(fit["alpha"], 6),
    }


def verdict(
    growth: dict[str, Any],
    config: dict[str, Any],
) -> tuple[str, str]:
    """Apply pre-registered P7 thresholds to the growth analysis."""
    if growth.get("verdict") == "insufficient_data":
        return "insufficient_data", growth["verdict_reason"]

    claim7_cfg = config.get("claim7", {})
    min_growth_pct_per_quarter = float(
        claim7_cfg.get("min_growth_pct_per_quarter", 1.0)
    )
    min_latest_fraction = float(claim7_cfg.get("min_latest_fraction", 0.001))

    slope_pct = growth["slope_pct_per_quarter"]
    latest = growth["latest_fraction"]

    if slope_pct >= min_growth_pct_per_quarter and latest >= min_latest_fraction:
        return (
            "soap_adoption_growing",
            (
                f"SOAP fraction growing at {slope_pct:.2f} pp/quarter "
                f"(threshold: {min_growth_pct_per_quarter} pp/quarter); "
                f"latest fraction: {latest:.3%}"
            ),
        )
    elif latest < min_latest_fraction:
        return (
            "soap_adoption_negligible",
            (
                f"SOAP fraction ({latest:.4%}) below minimum threshold "
                f"({min_latest_fraction:.3%}); "
                "ASIC participation in Quai workshares is currently negligible"
            ),
        )
    else:
        return (
            "soap_adoption_stalled",
            (
                f"SOAP fraction growth ({slope_pct:.2f} pp/quarter) below threshold "
                f"({min_growth_pct_per_quarter} pp/quarter); "
                f"adoption may have plateaued at {latest:.3%}"
            ),
        )


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def render_markdown(
    growth: dict[str, Any],
    v: str | None = None,
    v_reason: str | None = None,
    *,
    synthetic: bool = False,
) -> str:
    """Render Claim 7 results as markdown.

    Can be called as render_markdown(growth, v, v_reason, synthetic=...) from
    main(), or as render_markdown(result_dict, synthetic=...) from tests where
    the result dict already contains 'verdict' and 'verdict_reason'.
    """
    if v is None:
        v = growth.get("verdict", "insufficient_data")
    if v_reason is None:
        v_reason = growth.get("verdict_reason", "")
    lines: list[str] = []
    if synthetic:
        lines.append(
            "> **SYNTHETIC SAMPLE DATA** - pipeline demonstration only, not a finding.\n"
        )
    lines.append("# Claim 7: SOAP + TWP Adoption Rate as Energy Anchor Leading Indicator\n")
    lines.append(
        "Project SOAP (Dec 2025) allows SHA-256 ASICs (BCH/BTC), Scrypt ASICs (LTC/DOGE), "
        "and Ravencoin KawPoW GPUs to submit workshares to Quai blocks, earning QUAI rewards "
        "for the same work. The Quai team has confirmed that **Tensor Work Proof (TWP) inference** "
        "will also be added as a first-class merge-mining algorithm, meaning GPU inference nodes "
        "running InferenceGemm will earn Qi rewards as native Quai miners. "
        "This claim tracks whether SOAP and TWP participation is growing — a direct on-chain "
        "signal that the energy anchor is broadening beyond KawPoW GPUs.\n"
    )

    if growth.get("verdict") == "insufficient_data":
        lines.append(f"## Status: `{v}`\n")
        lines.append(f"{v_reason}\n")
        lines.append(
            "> SOAP launched ~Dec 2025. At least 90 days of on-chain workshare data "
            "are needed to compute a reliable trend. Run `python3 fetch_data.py` to "
            "extend the cache, then rerun.\n"
        )
        return "\n".join(lines)

    lines.append("## SOAP adoption trend\n")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| Analysis window | {growth['date_start']} → {growth['date_end']} ({growth['n_days']} days) |")
    lines.append(f"| Baseline SOAP fraction | {growth['baseline_fraction']:.4%} |")
    lines.append(f"| Latest SOAP fraction | **{growth['latest_fraction']:.4%}** |")
    lines.append(f"| Growth rate | {growth['slope_pct_per_quarter']:.2f} pp/quarter |")
    lines.append(f"| Trend R² | {growth['r_squared']:.3f} |\n")

    lines.append(f"## Verdict: `{v}`\n")
    lines.append(f"{v_reason}\n")

    lines.append("## What this means for the energy anchor\n")
    lines.append(
        "| SOAP fraction | Interpretation |\n"
        "| --- | --- |\n"
        "| < 0.1% | Negligible — energy anchor is KawPoW-only |\n"
        "| 0.1% – 1% | Early adoption — ASIC participation beginning |\n"
        "| 1% – 10% | Material — energy anchor meaningfully diversified |\n"
        "| > 10% | Significant — Bitcoin-scale SHA-256 energy contributing |\n"
    )

    lines.append(
        "> **Why this matters for Claim 6:** as SOAP and TWP adoption grows, the "
        "inference node becomes a native Quai miner. For SOAP: the ASIC + GPU split "
        "(ASIC handles workshares, GPU handles inference) becomes more common. For TWP: "
        "the GPU itself submits TWP receipts as workshares — no ASIC needed. "
        "The Bitcoin-scale scenarios in `claim6.md` show the dual-revenue economics at "
        "each adoption level. Claim 7 is the empirical complement: it tracks whether "
        "those scenarios are becoming reality.\n"
    )

    lines.append(
        "> **Merge-mining note:** SOAP workshares do not require Bitcoin miners to "
        "change their primary chain. A SHA-256 ASIC mining BTC submits the same hash "
        "to Quai as a workshare with negligible overhead. TWP workshares are even simpler: "
        "the InferenceGemm harness emits a Tensor Work Receipt as a byproduct of every "
        "inference run — no separate mining process required. The barrier to adoption is "
        "pool/harness software support and the Qi reward being worth the implementation "
        "cost — not any change to Bitcoin's or any other chain's protocol.\n"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Convenience wrapper (used by tests and reproduce.py)
# ---------------------------------------------------------------------------

def analyze(
    config: dict[str, Any],
    kawpow_ws: dict[str, float],
    soap_ws: dict[str, float],
    block_difficulty: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Run the full Claim 7 analysis and return a flat result dict.

    If block_difficulty is None, a synthetic constant series is used so that
    the SOAP fraction is computed purely from workshare difficulty.
    """
    if block_difficulty is None:
        # Use a constant block difficulty equal to the mean kawpow_ws value
        # so the fraction is dominated by the workshare signal.
        mean_kw = sum(kawpow_ws.values()) / max(len(kawpow_ws), 1)
        block_difficulty = {d: mean_kw * 10 for d in kawpow_ws}

    claim7_cfg = config.get("claim7", {})
    min_samples = int(claim7_cfg.get("min_samples", 90))

    fraction_series = soap_fraction_series(kawpow_ws, soap_ws, block_difficulty)
    growth = growth_rate_analysis(fraction_series, min_samples=min_samples)
    v, v_reason = verdict(growth, config)

    return {
        **growth,
        "verdict": v,
        "verdict_reason": v_reason,
        # Flatten key fields for test assertions
        "soap_fraction_latest": growth.get("latest_fraction", 0.0),
        "soap_fraction_baseline": growth.get("baseline_fraction", 0.0),
        "slope_pct_per_quarter": growth.get("slope_pct_per_quarter", 0.0),
        "r_squared": growth.get("r_squared", 0.0),
        "n_days": growth.get("n_days", 0),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Claim 7: SOAP adoption rate as energy anchor leading indicator"
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

    # Load workshare difficulty series
    kawpow_cache = read_cache(data_dir, "workshare_difficulty_kawpow_ws")
    soap_cache = read_cache(data_dir, "workshare_difficulty_soap_ws")
    diff_cache = read_cache(data_dir, "difficulty")

    if kawpow_cache is None or soap_cache is None or diff_cache is None:
        print(
            "missing workshare difficulty cache - "
            "run `python3 fetch_data.py` first"
        )
        return 1

    kawpow_ws = {d: float(v) for d, v in kawpow_cache["series"].items()}
    soap_ws = {d: float(v) for d, v in soap_cache["series"].items()}
    block_difficulty = {d: float(v) for d, v in diff_cache["series"].items()}

    # Filter to post-SOAP-launch dates only
    kawpow_ws = {d: v for d, v in kawpow_ws.items() if d >= SOAP_LAUNCH_DATE}
    soap_ws = {d: v for d, v in soap_ws.items() if d >= SOAP_LAUNCH_DATE}
    block_difficulty = {d: v for d, v in block_difficulty.items() if d >= SOAP_LAUNCH_DATE}

    claim7_cfg = config.get("claim7", {})
    min_samples = int(claim7_cfg.get("min_samples", 90))

    fraction_series = soap_fraction_series(kawpow_ws, soap_ws, block_difficulty)
    growth = growth_rate_analysis(fraction_series, min_samples=min_samples)
    v, v_reason = verdict(growth, config)

    results_dir = Path(config.get("results_dir", "results"))
    results_dir.mkdir(parents=True, exist_ok=True)

    stats = {
        **growth,
        "verdict": v,
        "verdict_reason": v_reason,
        "synthetic": args.sample,
        "soap_launch_date": SOAP_LAUNCH_DATE,
    }
    (results_dir / "claim7_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf-8"
    )

    markdown = render_markdown(growth, v, v_reason, synthetic=args.sample)
    (results_dir / "claim7.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    print("claim7: written to results/claim7.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
