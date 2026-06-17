"""Claim 5 — Miner token choice, exchange-rate directionality, and thesis robustness.

This module tests three related empirical questions that arise from the observation
that Quai miners choose their block reward denomination (QUAI or Qi) at block time,
yet the work is identical regardless of choice:

  P5a — Token-choice neutrality
        The energy-money thesis holds regardless of miner token preference because
        the on-chain K-Quai controller maintains QUAI↔Qi convertibility at the
        protocol-set rate.  Concretely: the Qi-per-QUAI exchange rate (on-chain)
        should move in the direction predicted by the controller's logistic
        regression — rising when miners prefer QUAI (lock=0), falling when miners
        prefer Qi (lock=1).

  P5b — Directionality (Granger causality proxy)
        A sustained shift in the 4,000-block rolling miner preference toward QUAI
        should *precede* an upward adjustment in the on-chain exchange rate.
        We test this with a lagged cross-correlation: corr(Δ exchange_rate[t],
        qi_fraction[t-k]) for k in {1..14} days.  The thesis predicts a negative
        peak correlation at some lag k > 0 (more QUAI preference → lower
        qi_fraction → subsequent rate increase).

  P5c — Market-rate convergence
        The market-implied exchange rate (QUAI_USD / QI_USD from CoinGecko, when
        available) should track the on-chain protocol rate within a bounded band.
        Wide, persistent divergence would indicate the controller is failing to
        anchor the peg.  When the QI market price is unavailable (no CoinGecko
        listing yet), this sub-claim is reported as "insufficient_data".

Usage:
    python3 claim5_token_choice.py [--data data/] [--results results/] [--config research.yaml]
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any

import yaml  # type: ignore

from fetch_data import load_research_config, read_cache
from series import align_by_date, log_returns  # noqa: F401  (log_returns available for future use)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_series(data_dir: Path, name: str) -> dict[str, float]:
    cache = read_cache(data_dir, name)
    if cache is None:
        return {}
    return {k: float(v) for k, v in cache["series"].items()}


def _is_synthetic(data_dir: Path, *names: str) -> bool:
    for name in names:
        cache = read_cache(data_dir, name)
        if cache and cache.get("synthetic"):
            return True
    return False


def _banner(synthetic: bool) -> str:
    if synthetic:
        return (
            "> **SYNTHETIC DATA — results below are illustrative only and must not "
            "be cited as empirical findings.**\n"
        )
    return ""


def _rolling_mean(series: list[float], window: int) -> list[float]:
    """Simple rolling mean; first (window-1) values use available data."""
    out = []
    for i, _ in enumerate(series):
        start = max(0, i - window + 1)
        out.append(statistics.mean(series[start : i + 1]))
    return out


def _lagged_corr(x: list[float], y: list[float], max_lag: int = 14) -> list[tuple[int, float]]:
    """Pearson correlation of x[t] with y[t-k] for k in 1..max_lag.

    Returns list of (lag, correlation) pairs.  Requires len(x) == len(y).
    """
    n = len(x)
    results = []
    for lag in range(1, max_lag + 1):
        if n - lag < 5:
            break
        xs = x[lag:]
        ys = y[: n - lag]
        if len(xs) < 5:
            break
        mx, my = statistics.mean(xs), statistics.mean(ys)
        num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
        denom = math.sqrt(
            sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys)
        )
        corr = num / denom if denom > 1e-12 else 0.0
        results.append((lag, corr))
    return results


# ---------------------------------------------------------------------------
# Sub-claim analysis functions
# ---------------------------------------------------------------------------

def analyse_p5a(
    qi_fraction: dict[str, float],
    exchange_rate: dict[str, float],
) -> dict[str, Any]:
    """P5a: Does the exchange rate move in the direction the controller predicts?

    When qi_fraction is low (miners prefer QUAI), the controller should
    *increase* the Qi-per-QUAI rate to make Qi more attractive.
    We test: sign(Δ exchange_rate) negatively correlated with qi_fraction.
    """
    dates = sorted(set(qi_fraction) & set(exchange_rate))
    if len(dates) < 10:
        return {"status": "insufficient_data", "n": len(dates)}

    frac = [qi_fraction[d] for d in dates]
    er = [exchange_rate[d] for d in dates]

    # Day-over-day change in exchange rate
    delta_er = [er[i] - er[i - 1] for i in range(1, len(er))]
    frac_lagged = frac[: len(delta_er)]  # qi_fraction[t-1] predicts Δer[t]

    if len(delta_er) < 5:
        return {"status": "insufficient_data", "n": len(delta_er)}

    # Pearson correlation between qi_fraction[t-1] and Δexchange_rate[t]
    mx = statistics.mean(frac_lagged)
    my = statistics.mean(delta_er)
    num = sum((a - mx) * (b - my) for a, b in zip(frac_lagged, delta_er))
    denom = math.sqrt(
        sum((a - mx) ** 2 for a in frac_lagged)
        * sum((b - my) ** 2 for b in delta_er)
    )
    corr = num / denom if denom > 1e-12 else 0.0

    # Thesis predicts corr < 0 (more QUAI preference → rate rises)
    direction_correct = corr < 0

    return {
        "status": "ok",
        "n": len(delta_er),
        "corr_qi_fraction_vs_delta_er": round(corr, 4),
        "direction_correct": direction_correct,
        "mean_qi_fraction": round(statistics.mean(frac), 4),
        "mean_er_qi_per_quai": round(statistics.mean(er), 4),
        "latest_er_qi_per_quai": round(er[-1], 4),
    }


def analyse_p5b(
    qi_fraction: dict[str, float],
    exchange_rate: dict[str, float],
    max_lag: int = 14,
) -> dict[str, Any]:
    """P5b: Does miner preference *lead* exchange rate adjustments?"""
    dates = sorted(set(qi_fraction) & set(exchange_rate))
    if len(dates) < max_lag + 5:
        return {"status": "insufficient_data", "n": len(dates)}

    frac = [qi_fraction[d] for d in dates]
    er = [exchange_rate[d] for d in dates]
    delta_er = [er[i] - er[i - 1] for i in range(1, len(er))]
    frac_aligned = frac[: len(delta_er)]

    lag_corrs = _lagged_corr(delta_er, frac_aligned, max_lag=max_lag)
    if not lag_corrs:
        return {"status": "insufficient_data", "n": len(delta_er)}

    # Find the lag with the most negative correlation (strongest leading signal)
    best_lag, best_corr = min(lag_corrs, key=lambda x: x[1])
    # Thesis predicts best_corr < 0 at some lag > 0
    leading_signal = best_corr < -0.05

    return {
        "status": "ok",
        "n": len(delta_er),
        "best_lag_days": best_lag,
        "best_lag_corr": round(best_corr, 4),
        "leading_signal_detected": leading_signal,
        "lag_correlations": [(k, round(c, 4)) for k, c in lag_corrs],
    }


def analyse_p5c(
    quai_usd: dict[str, float],
    qi_usd: dict[str, float],
    exchange_rate: dict[str, float],
) -> dict[str, Any]:
    """P5c: Does the market-implied rate track the on-chain protocol rate?"""
    if not qi_usd:
        return {
            "status": "insufficient_data",
            "reason": "QI market price unavailable (no CoinGecko listing found)",
        }

    dates = sorted(set(quai_usd) & set(qi_usd) & set(exchange_rate))
    if len(dates) < 10:
        return {"status": "insufficient_data", "n": len(dates)}

    market_implied = {
        d: quai_usd[d] / qi_usd[d] for d in dates if qi_usd[d] > 1e-12
    }
    on_chain = {d: exchange_rate[d] for d in market_implied}

    if len(market_implied) < 10:
        return {"status": "insufficient_data", "n": len(market_implied)}

    ratios = [market_implied[d] / on_chain[d] for d in sorted(market_implied) if on_chain[d] > 0]
    mean_ratio = statistics.mean(ratios)
    max_deviation = max(abs(r - 1.0) for r in ratios)

    return {
        "status": "ok",
        "n": len(ratios),
        "mean_market_vs_onchain_ratio": round(mean_ratio, 4),
        "max_deviation_pct": round(max_deviation * 100, 2),
        "within_20pct_band": max_deviation < 0.20,
    }


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def build_markdown(
    p5a: dict[str, Any],
    p5b: dict[str, Any],
    p5c: dict[str, Any],
    synthetic: bool,
    config: dict[str, Any],
) -> str:
    frozen = config.get("verdict", {}).get("thresholds_frozen", False)
    draft_stamp = "" if frozen else "\n> **THRESHOLDS DRAFT — not citable until `thresholds_frozen: true` in research.yaml.**\n"
    banner = _banner(synthetic)

    lines: list[str] = []
    lines.append("# Claim 5 — Miner Token Choice, Directionality & Thesis Robustness\n")
    lines.append(banner)
    lines.append(draft_stamp)
    lines.append(
        "Quai miners elect their block reward denomination (QUAI or Qi) at block time via the "
        "`woHeader.lock` field. The work is identical regardless of choice. This claim tests "
        "whether the on-chain K-Quai controller responds to miner preference as the monetary "
        "theory predicts, and whether that directionality preserves the energy-money thesis "
        "under any miner preference regime.\n"
    )

    # --- P5a ---
    lines.append("## P5a — Controller Directionality\n")
    lines.append(
        "**Prediction:** When miners prefer QUAI (low `qi_fraction`), the on-chain exchange "
        "rate (Qi-per-QUAI) should rise, making Qi more attractive and restoring equilibrium. "
        "We expect `corr(qi_fraction[t-1], Δexchange_rate[t]) < 0`.\n"
    )
    if p5a["status"] == "insufficient_data":
        lines.append(f"**Result:** `insufficient_data` (n={p5a.get('n', 0)} aligned observations)\n")
    else:
        corr = p5a["corr_qi_fraction_vs_delta_er"]
        direction = p5a["direction_correct"]
        lines.append(f"| Metric | Value |")
        lines.append(f"|---|---|")
        lines.append(f"| Observations | {p5a['n']} |")
        lines.append(f"| Mean Qi-fraction (miner preference) | {p5a['mean_qi_fraction']:.4f} |")
        lines.append(f"| Latest on-chain rate (Qi per QUAI) | {p5a['latest_er_qi_per_quai']:.4f} |")
        lines.append(f"| corr(qi_fraction[t-1], Δrate[t]) | {corr:.4f} |")
        lines.append(f"| Direction correct (corr < 0) | {'✓ Yes' if direction else '✗ No'} |\n")
        verdict = "**supports_directionality**" if direction else "**contradicts_directionality**"
        lines.append(f"**Verdict:** {verdict}\n")

    # --- P5b ---
    lines.append("## P5b — Miner Preference Leads Rate Adjustments\n")
    lines.append(
        "**Prediction:** A shift in miner preference should *precede* the exchange rate "
        "adjustment by at least 1 day (the controller observes a 4,000-block rolling window). "
        "We look for a negative lagged cross-correlation peak at lag k > 0.\n"
    )
    if p5b["status"] == "insufficient_data":
        lines.append(f"**Result:** `insufficient_data` (n={p5b.get('n', 0)} observations)\n")
    else:
        lines.append(f"| Metric | Value |")
        lines.append(f"|---|---|")
        lines.append(f"| Observations | {p5b['n']} |")
        lines.append(f"| Best lag (days) | {p5b['best_lag_days']} |")
        lines.append(f"| Best lag correlation | {p5b['best_lag_corr']:.4f} |")
        lines.append(f"| Leading signal detected (corr < -0.05) | {'✓ Yes' if p5b['leading_signal_detected'] else '✗ No'} |\n")
        lines.append("**Lag correlation table (Δrate[t] vs qi_fraction[t-k]):**\n")
        lines.append("| Lag (days) | Correlation |")
        lines.append("|---|---|")
        for lag, corr in p5b["lag_correlations"]:
            lines.append(f"| {lag} | {corr:.4f} |")
        lines.append("")
        verdict = "**leading_signal_confirmed**" if p5b["leading_signal_detected"] else "**no_leading_signal**"
        lines.append(f"**Verdict:** {verdict}\n")

    # --- P5c ---
    lines.append("## P5c — Market Rate Tracks On-Chain Protocol Rate\n")
    lines.append(
        "**Prediction:** The market-implied exchange rate (QUAI_USD / QI_USD) should track "
        "the on-chain K-Quai controller rate within a ±20% band. Wide persistent divergence "
        "would indicate the controller is failing to anchor the peg.\n"
    )
    if p5c["status"] == "insufficient_data":
        reason = p5c.get("reason", f"n={p5c.get('n', 0)} aligned observations")
        lines.append(f"**Result:** `insufficient_data` — {reason}\n")
    else:
        lines.append(f"| Metric | Value |")
        lines.append(f"|---|---|")
        lines.append(f"| Observations | {p5c['n']} |")
        lines.append(f"| Mean market/on-chain ratio | {p5c['mean_market_vs_onchain_ratio']:.4f} |")
        lines.append(f"| Max deviation from parity | {p5c['max_deviation_pct']:.2f}% |")
        lines.append(f"| Within ±20% band | {'✓ Yes' if p5c['within_20pct_band'] else '✗ No'} |\n")
        verdict = "**peg_tracking**" if p5c["within_20pct_band"] else "**peg_divergence**"
        lines.append(f"**Verdict:** {verdict}\n")

    # --- Thesis robustness note ---
    lines.append("## Thesis Robustness Under Any Miner Preference\n")
    lines.append(
        "The energy-money thesis does not require miners to prefer Qi. Because QUAI and Qi "
        "are convertible at the protocol rate, the total energy expenditure of the network "
        "(captured by difficulty) is always fully reflected in the combined monetary base. "
        "Miner token choice is a *signal* about relative value expectations, not a threat "
        "to the energy anchor. The K-Quai controller's logistic regression continuously "
        "adjusts the exchange rate to maintain equilibrium, meaning:\n\n"
        "- A sustained preference for QUAI raises the Qi-per-QUAI rate → Qi becomes cheaper "
        "relative to energy cost → inference priced in Qi becomes more competitive.\n"
        "- A sustained preference for Qi contracts Qi supply → Qi price rises toward energy "
        "cost → the energy peg tightens.\n\n"
        "In both cases, the system self-corrects. The miner token choice ratio is therefore "
        "a **leading indicator of peg pressure**, not a failure mode.\n"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(config: dict[str, Any], data_dir: Path, results_dir: Path) -> dict[str, Any]:
    qi_fraction = _load_series(data_dir, "token_choice_qi_fraction")
    exchange_rate = _load_series(data_dir, "exchange_rate_qi_per_quai")
    quai_usd = _load_series(data_dir, "qi_usd")  # note: CoinGecko 'quai-network' is QUAI
    qi_usd = _load_series(data_dir, "qi_usd_qi_token")  # separate Qi token price if available

    synthetic = _is_synthetic(data_dir, "token_choice_qi_fraction", "exchange_rate_qi_per_quai")

    p5a = analyse_p5a(qi_fraction, exchange_rate)
    p5b = analyse_p5b(qi_fraction, exchange_rate)
    p5c = analyse_p5c(quai_usd, qi_usd, exchange_rate)

    md = build_markdown(p5a, p5b, p5c, synthetic, config)
    results_dir.mkdir(parents=True, exist_ok=True)
    out_path = results_dir / "claim5.md"
    out_path.write_text(md, encoding="utf-8")

    return {
        "p5a": p5a,
        "p5b": p5b,
        "p5c": p5c,
        "synthetic": synthetic,
        "output": str(out_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run claim 5 — token choice & directionality")
    parser.add_argument("--config", default="research.yaml")
    parser.add_argument("--data", default=None)
    parser.add_argument("--results", default=None)
    parser.add_argument("--sample", action="store_true", help="Use synthetic sample data from data/sample/")
    args = parser.parse_args()
    config = load_research_config(args.config)
    if args.sample:
        data_dir = Path(config.get("data_dir", "data")) / "sample"
    else:
        data_dir = Path(args.data or config.get("data_dir", "data"))
    results_dir = Path(args.results or config.get("results_dir", "results"))
    result = run(config, data_dir, results_dir)
    print(f"claim5: written to {result['output']}")
    print(f"  P5a: {result['p5a']}")
    print(f"  P5b: {result['p5b']}")
    print(f"  P5c: {result['p5c']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
