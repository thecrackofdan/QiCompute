"""QiCompute live dashboard.

Prints a single-screen at-a-glance view of the project's current state
without running the full pipeline. Reads from cached data and results files.

Usage:
    python3 qi_dashboard.py              # live cache
    python3 qi_dashboard.py --sample     # synthetic fixtures
    python3 qi_dashboard.py --watch 60   # refresh every 60 seconds
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from fetch_data import load_research_config, read_cache

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _age(iso_ts: str | None) -> str:
    """Return a human-readable age string for an ISO timestamp."""
    if not iso_ts:
        return "unknown"
    try:
        ts = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - ts
        days = delta.days
        hours = delta.seconds // 3600
        if days > 0:
            return f"{days}d {hours}h ago"
        minutes = delta.seconds // 60
        if hours > 0:
            return f"{hours}h {minutes % 60}m ago"
        return f"{minutes}m ago"
    except Exception:
        return iso_ts


def _bar(fraction: float, width: int = 20) -> str:
    """ASCII progress bar."""
    filled = int(min(max(fraction, 0.0), 1.0) * width)
    return "[" + "█" * filled + "░" * (width - filled) + "]"


def _verdict_icon(verdict: str | None) -> str:
    icons = {
        "supports_energy_thesis": "✓",
        "energy_thesis_not_supported": "✗",
        "below_liquidity_threshold": "~",
        "insufficient_data": "?",
        "dual_revenue_non_trivial": "✓",
        "dual_revenue_below_threshold": "✗",
    }
    return icons.get(verdict or "", "?")


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Dashboard sections
# ---------------------------------------------------------------------------

def section_header() -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        "╔══════════════════════════════════════════════════════════════╗\n"
        f"║           QiCompute Dashboard  —  {now}  ║\n"
        "╚══════════════════════════════════════════════════════════════╝"
    )


def section_qi_index(results_dir: Path, data_dir: Path) -> str:
    lines = ["── Qi Index (Claim 3 derived) " + "─" * 33]
    index_path = results_dir / "qi_index.json"
    index = _load_json(index_path)
    if index:
        synth = " [SYNTHETIC]" if index.get("synthetic") else ""
        lines.append(f"  As of:          {index.get('as_of', '?')}{synth}")
        lines.append(f"  Qi cost 1M tok: {index.get('qi_cost', '?')} Qi")
        lines.append(f"  Joules / Qi:    {index.get('joules_per_qi', '?'):.0f} J")
        lines.append(f"  Joules / token: {index.get('joules_per_token', '?')} J  ({index.get('joules_per_token_source', '')})")
    else:
        lines.append("  No qi_index.json — run `python3 qi_index.py` first")
    return "\n".join(lines)


def section_claim1(results_dir: Path) -> str:
    lines = ["── Claim 1: Peg Tracking " + "─" * 38]
    stats = _load_json(results_dir / "claim1_stats.json")
    if stats:
        verdict = stats.get("verdict", "?")
        icon = _verdict_icon(verdict)
        draft = " [DRAFT]" if not stats.get("thresholds_frozen") else ""
        lines.append(f"  Verdict:        {icon} {verdict}{draft}")
        lines.append(f"  Reason:         {stats.get('verdict_reason', '?')}")
        r2_energy = stats.get("r2_energy_cost")
        r2_btc = stats.get("r2_btc")
        r2_eth = stats.get("r2_eth")
        if r2_energy is not None:
            lines.append(f"  R² energy:      {r2_energy:.4f}")
        if r2_btc is not None:
            lines.append(f"  R² BTC (null):  {r2_btc:.4f}")
        if r2_eth is not None:
            lines.append(f"  R² ETH (null):  {r2_eth:.4f}")
        n = stats.get("n_observations")
        if n:
            lines.append(f"  Observations:   {n} days")
        vol = stats.get("median_daily_volume_usd")
        if vol:
            lines.append(f"  Median volume:  ${vol:,.0f}/day")
        multi = stats.get("multi_algo_energy")
        if multi:
            lines.append(f"  Energy model:   multi-algorithm ({multi})")
    else:
        lines.append("  No claim1_stats.json — run `python3 claim1_peg.py` first")
    return "\n".join(lines)


def section_claim5(results_dir: Path) -> str:
    lines = ["── Claim 5: K-Quai Controller " + "─" * 33]
    stats = _load_json(results_dir / "claim5_stats.json")
    if stats:
        for sub in ("p5a", "p5b", "p5c"):
            sub_data = stats.get(sub, {})
            status = sub_data.get("status", "?")
            if sub == "p5a":
                detail = f"corr={sub_data.get('corr_qi_fraction_vs_delta_er', '?'):.4f}, direction_correct={sub_data.get('direction_correct', '?')}"
            elif sub == "p5b":
                detail = f"best_lag={sub_data.get('best_lag_days', '?')}d, leading={sub_data.get('leading_signal_detected', '?')}"
            else:
                detail = sub_data.get("reason", f"corr={sub_data.get('market_onchain_corr', '?')}")
            lines.append(f"  {sub.upper()}: {status:20s} {detail}")
        qi_frac = stats.get("mean_qi_fraction")
        er = stats.get("mean_er_qi_per_quai")
        if qi_frac is not None:
            lines.append(f"  Avg Qi-elect:   {qi_frac:.1%} of blocks")
        if er is not None:
            lines.append(f"  Avg on-chain ER: {er:.2f} Qi/QUAI")
    else:
        lines.append("  No claim5_stats.json — run `python3 claim5_token_choice.py` first")
    return "\n".join(lines)


def section_claim6(results_dir: Path) -> str:
    lines = ["── Claim 6: Dual-Revenue Model " + "─" * 32]
    stats = _load_json(results_dir / "claim6_stats.json")
    if stats:
        verdict = stats.get("verdict", "?")
        icon = _verdict_icon(verdict)
        coverage = stats.get("workshare_coverage_fraction", 0.0)
        breakeven = stats.get("breakeven_utilisation_fraction", 1.0)
        lines.append(f"  Verdict:        {icon} {verdict}")
        lines.append(f"  WS coverage:    {_bar(coverage)} {coverage:.1%}")
        lines.append(f"  Break-even:     {_bar(breakeven)} {breakeven:.1%} utilisation")
        lines.append(f"  WS Qi/day:      {stats.get('workshare_qi_per_day', '?'):.4f} Qi")
        lines.append(f"  Energy Qi/day:  {stats.get('energy_cost_qi_per_day', '?'):.4f} Qi")
        lines.append(f"  WS/day:         {stats.get('expected_workshares_per_day', '?'):.1f}")
    else:
        lines.append("  No claim6_stats.json — run `python3 claim6_workshare_inference.py` first")
    return "\n".join(lines)


def section_data_freshness(data_dir: Path) -> str:
    lines = ["── Data Cache Freshness " + "─" * 39]
    datasets = [
        ("qi_usd", "Qi price"),
        ("btc_usd", "BTC price"),
        ("eth_usd", "ETH price"),
        ("difficulty", "Quai difficulty"),
        ("token_choice_qi_fraction", "Miner token choice"),
        ("exchange_rate_qi_per_quai", "On-chain exchange rate"),
        ("workshare_difficulty_kawpow_ws", "KawPoW workshares"),
        ("workshare_difficulty_soap_ws", "SOAP workshares"),
        ("electricity", "Electricity (EIA)"),
    ]
    for cache_name, label in datasets:
        path = data_dir / f"{cache_name}.json"
        if path.exists():
            try:
                meta = json.loads(path.read_text(encoding="utf-8"))
                fetched = meta.get("fetched_at") or meta.get("timestamp", "")
                n = len(meta.get("series", {}))
                lines.append(f"  {label:30s} {n:5d} pts  {_age(fetched)}")
            except Exception:
                lines.append(f"  {label:30s} (unreadable)")
        else:
            lines.append(f"  {label:30s} missing")
    return "\n".join(lines)


def section_pipeline_status(results_dir: Path) -> str:
    lines = ["── Pipeline Status " + "─" * 44]
    artifacts = [
        ("claim1.md", "Claim 1 markdown"),
        ("claim1_stats.json", "Claim 1 stats"),
        ("claim2.md", "Claim 2 markdown"),
        ("claim5.md", "Claim 5 markdown"),
        ("claim5_stats.json", "Claim 5 stats"),
        ("claim6.md", "Claim 6 markdown"),
        ("claim6_stats.json", "Claim 6 stats"),
        ("qi_index.json", "Qi index"),
        ("REPORT.md", "Full report"),
    ]
    for filename, label in artifacts:
        path = results_dir / filename
        if path.exists():
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            age = _age(mtime.isoformat())
            lines.append(f"  ✓ {label:30s} {age}")
        else:
            lines.append(f"  ✗ {label:30s} missing")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def render_dashboard(config: dict, *, sample: bool) -> str:
    data_dir = Path("data/sample" if sample else config.get("data_dir", "data"))
    results_dir = Path(config.get("results_dir", "results"))

    parts = [
        section_header(),
        "",
        section_qi_index(results_dir, data_dir),
        "",
        section_claim1(results_dir),
        "",
        section_claim5(results_dir),
        "",
        section_claim6(results_dir),
        "",
        section_data_freshness(data_dir),
        "",
        section_pipeline_status(results_dir),
        "",
        "  Run `python3 reproduce.py` to refresh all claims.",
        "  Run `python3 reproduce.py --sample` for an offline demo.",
    ]
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="QiCompute live dashboard")
    parser.add_argument("--config", default="research.yaml")
    parser.add_argument("--sample", action="store_true", help="Use synthetic fixtures")
    parser.add_argument(
        "--watch",
        type=int,
        metavar="SECONDS",
        help="Refresh every N seconds (Ctrl-C to stop)",
    )
    args = parser.parse_args()
    config = load_research_config(args.config)

    if args.watch:
        try:
            while True:
                # Clear screen
                os.system("clear" if os.name != "nt" else "cls")
                print(render_dashboard(config, sample=args.sample))
                print(f"\n  [refreshing every {args.watch}s — Ctrl-C to stop]")
                time.sleep(args.watch)
        except KeyboardInterrupt:
            print("\nDashboard stopped.")
            return 0
    else:
        print(render_dashboard(config, sample=args.sample))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
