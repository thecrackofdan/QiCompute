"""Claim 2: is energy-marginal compute more stably priced in Qi than in USD or BTC?

    python3 claim2_stability.py            # cached real data
    python3 claim2_stability.py --sample   # SYNTHETIC fixtures, pipeline testing only

Two fixed bundles are priced every day through market exchange rates:
  - 1 kWh of compute energy
  - 1M tokens of Llama-70B-class inference (joules/token from measurements.db
    if benchmark.py --store has real rows; otherwise the labeled config fallback)

Each bundle's daily price is expressed in USD, BTC, and Qi, and the chart
compares rolling 30-day volatility of each denomination.

THE COROLLARY, RESPECTED: the series that the thesis predicts is stable is
Qi per JOULE. Qi per TOKEN must fall over time as joules/token falls with
hardware and software efficiency - Qi prices the energy input of compute,
not the output. Both are presented; today they differ only by the current
joules/token scale factor because the measured efficiency history is still
a single point. As measurements.db accumulates rows over time, the token
series will diverge downward from the energy series, and that divergence is
expected, not a failure of the thesis.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Any

from claim1_peg import load_inputs
from fetch_data import load_research_config, read_cache
from series import mean, rolling_volatility


def latest_measured_joules_per_token(db_path: str = "measurements.db") -> float | None:
    if not Path(db_path).exists():
        return None
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT joules_per_token FROM measurements WHERE joules_per_token > 0 ORDER BY ts DESC LIMIT 1"
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()
    return float(row[0]) if row else None


def electricity_series(
    config: dict[str, Any], dates: list[str], *, sample: bool, max_forward_fill_days: int = 90
) -> tuple[dict[str, float], str]:
    """Return a daily electricity price series for the given dates.

    Monthly EIA data is forward-filled onto daily dates. If the most recent
    cached month is more than `max_forward_fill_days` before the last
    requested date, a stale-data warning is included in the source label
    and printed to stderr so the user knows the claim 2 bundle prices are
    extrapolated beyond the configured threshold.
    """
    data_dir = Path("data/sample" if sample else config.get("data_dir", "data"))
    cached = read_cache(data_dir, "electricity_usd_per_kwh")
    if cached and cached.get("series"):
        monthly = {date: float(value) for date, value in cached["series"].items()}
        # carry the latest known monthly price forward across days
        series = {}
        known = sorted(monthly)
        for date in dates:
            applicable = [k for k in known if k <= date]
            if applicable:
                series[date] = monthly[applicable[-1]]
        if series:
            latest_month = known[-1]
            last_date = dates[-1] if dates else latest_month
            # Warn if the forward-fill gap exceeds the configured threshold
            from datetime import date as _date
            try:
                gap_days = (_date.fromisoformat(last_date) - _date.fromisoformat(latest_month)).days
            except ValueError:
                gap_days = 0
            if gap_days > max_forward_fill_days:
                import sys
                print(
                    f"WARNING: electricity data last updated {latest_month}; "
                    f"forward-filling {gap_days} days to {last_date} "
                    f"(>{max_forward_fill_days}-day threshold). "
                    "Re-run fetch_data.py with an EIA API key for fresher data.",
                    file=sys.stderr,
                )
                source = (
                    f"EIA cached series (STALE: last month {latest_month}, "
                    f"forward-filled {gap_days}d to {last_date})"
                )
            else:
                source = "EIA cached series"
            return series, source
    flat = float(Decimal(str(config["electricity"]["fallback_usd_per_kwh"])))
    return {date: flat for date in dates}, f"flat fallback {flat} $/kWh (no EIA cache)"


def analyze(config: dict[str, Any], *, sample: bool) -> dict[str, Any] | None:
    inputs = load_inputs(config, sample=sample)
    if inputs is None:
        return None
    qi_usd, btc_usd = inputs["qi_usd"], inputs["btc_usd"]
    dates = sorted(set(qi_usd) & set(btc_usd))
    elec, elec_source = electricity_series(config, dates, sample=sample)
    dates = [d for d in dates if d in elec]

    jpt = latest_measured_joules_per_token()
    jpt_source = "measurements.db (benchmark.py --store)"
    if jpt is None:
        jpt = float(Decimal(str(config["claim2"]["joules_per_token_fallback"])))
        jpt_source = f"CONFIG FALLBACK {jpt} J/token - run benchmark.py --store for real data"
    token_bundle = int(config["claim2"].get("token_bundle", 1_000_000))
    bundle_joules = jpt * token_bundle

    # Daily USD cost of each bundle, then re-denominated through market rates.
    energy_usd = {d: 1.0 * elec[d] for d in dates}                      # 1 kWh
    tokens_usd = {d: bundle_joules / 3_600_000.0 * elec[d] for d in dates}

    denominations: dict[str, list[float]] = {
        "energy_bundle_usd": [energy_usd[d] for d in dates],
        "energy_bundle_btc": [energy_usd[d] / btc_usd[d] for d in dates],
        "energy_bundle_qi": [energy_usd[d] / qi_usd[d] for d in dates],
        "tokens_bundle_usd": [tokens_usd[d] for d in dates],
        "tokens_bundle_btc": [tokens_usd[d] / btc_usd[d] for d in dates],
        "tokens_bundle_qi": [tokens_usd[d] / qi_usd[d] for d in dates],
    }
    window = int(config["claim2"].get("rolling_window_days", 30))
    volatilities = {name: rolling_volatility(values, window) for name, values in denominations.items()}
    mean_vols = {
        name: round(mean([v for v in vols if v is not None]), 6)
        for name, vols in volatilities.items()
    }
    return {
        "dates": dates,
        "window_days": window,
        "joules_per_token": jpt,
        "joules_per_token_source": jpt_source,
        "electricity_source": elec_source,
        "token_bundle": token_bundle,
        "mean_rolling_volatility": mean_vols,
        "volatilities": volatilities,
        "denominations": denominations,
    }


def render_markdown(result: dict[str, Any], *, synthetic: bool) -> str:
    vols = result["mean_rolling_volatility"]
    lines = []
    if synthetic:
        lines += ["> **SYNTHETIC SAMPLE DATA - pipeline demonstration only, not a finding.**", ""]
    lines += [
        "# Claim 2: Unit-of-Account Stability",
        "",
        f"Rolling {result['window_days']}-day annualized volatility of two fixed compute bundles, "
        "each denominated in USD, BTC, and Qi (via market exchange rates).",
        "",
        f"- joules/token: {result['joules_per_token']} ({result['joules_per_token_source']})",
        f"- electricity series: {result['electricity_source']}",
        "",
        "| Bundle | in USD | in BTC | in Qi |",
        "| --- | --- | --- | --- |",
        f"| 1 kWh of compute energy | {vols['energy_bundle_usd']} | {vols['energy_bundle_btc']} | {vols['energy_bundle_qi']} |",
        f"| {result['token_bundle']:,} tokens | {vols['tokens_bundle_usd']} | {vols['tokens_bundle_btc']} | {vols['tokens_bundle_qi']} |",
        "",
        "Lower is more stable. The thesis predicts the Qi column wins **for the energy bundle**.",
        "",
        "## The corollary (read before quoting the token row)",
        "",
        "Qi prices the energy INPUT of compute, not the output. Qi/token must fall over time as "
        "joules/token falls with hardware and software efficiency, so token-bundle stability in Qi "
        "is NOT what the thesis predicts. Today the two rows differ only by a constant joules/token "
        "scale (one measurement point); as the public measurement dataset accumulates efficiency "
        "history, the token series will diverge downward from the energy series - expected, not a failure.",
        "",
    ]
    return "\n".join(lines)


def render_chart(result: dict[str, Any], path: str, *, synthetic: bool) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    dates = result["dates"]
    fig, ax = plt.subplots(figsize=(10, 5))
    labels = {
        "energy_bundle_usd": "1 kWh in USD",
        "energy_bundle_btc": "1 kWh in BTC",
        "energy_bundle_qi": "1 kWh in Qi",
    }
    for name, label in labels.items():
        ax.plot(dates, result["volatilities"][name], label=label)
    step = max(len(dates) // 10, 1)
    ax.set_xticks(dates[::step])
    ax.tick_params(axis="x", rotation=45)
    ax.set_ylabel(f"rolling {result['window_days']}d annualized volatility")
    title = "Claim 2: stability of 1 kWh of compute by denomination"
    if synthetic:
        title += "  [SYNTHETIC SAMPLE DATA]"
    ax.set_title(title)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Claim 2: unit-of-account stability")
    parser.add_argument("--config", default="research.yaml")
    parser.add_argument("--sample", action="store_true", help="Use synthetic sample fixtures (testing only)")
    args = parser.parse_args()
    config = load_research_config(args.config)
    result = analyze(config, sample=args.sample)
    if result is None:
        return 1
    results_dir = Path(config.get("results_dir", "results"))
    results_dir.mkdir(parents=True, exist_ok=True)
    stats = {k: v for k, v in result.items() if k not in {"volatilities", "denominations", "dates"}}
    stats["synthetic"] = args.sample
    (results_dir / "claim2_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    markdown = render_markdown(result, synthetic=args.sample)
    (results_dir / "claim2.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    if render_chart(result, str(results_dir / "claim2_stability.png"), synthetic=args.sample):
        print(f"chart: {results_dir}/claim2_stability.png")
    else:
        print("matplotlib not installed; chart skipped (pip install matplotlib)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
