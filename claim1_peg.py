"""Claim 1: does Qi's MARKET price track its modeled energy cost of production?

    python3 claim1_peg.py              # analyze cached real data (data/)
    python3 claim1_peg.py --sample     # SYNTHETIC fixtures, for testing the pipeline only

WHAT IS AND IS NOT UNDER TEST. Quai's protocol ties Qi emission to hashrate
and difficulty BY CONSTRUCTION - that coupling is mechanics, shared with
every proof-of-work asset, and is the premise here, not the finding. What
this script tests is MARKET-level coupling: whether Qi's exchange price
tracks the modeled energy cost of producing a Qi. Bitcoin proves identical
protocol mechanics do not pin market price to production cost, which is why
the null hypotheses are built in: Qi daily log-returns are regressed on
modeled cost-of-production returns AND on BTC and ETH returns (two crypto-
beta nulls; small-caps often track broad risk appetite more tightly than
BTC alone). The thesis is supported only if energy cost beats EVERY null;
if any null explains Qi better, the verdict says the thesis is not
supported.

NO-CONCLUSION GATES, applied before any verdict:
- fewer than verdict.min_samples aligned observations -> "insufficient_data"
- median daily volume below verdict.min_median_daily_volume_usd ->
  "below_liquidity_threshold" (a thin market's price is noise; stats are
  still printed for inspection but no conclusion is drawn either way)
Thin data is never smoothed into a conclusion.

Cost model: difficulty (hashes/block) / block_reward (Qi/block) = hashes/Qi;
divided by the reference GPU's hashrate gives seconds of work per Qi; times
watts gives joules per Qi; times $/kWh gives modeled USD cost per Qi.

WHAT THE COST-MODEL CONSTANTS CAN AND CANNOT AFFECT (honesty note): the
$/kWh, reference hashrate, and watts are constant multipliers on the cost
series, and constant multipliers CANCEL in log-returns. The returns-based
verdict is therefore invariant to them BY CONSTRUCTION - it cannot flip
under a different global-marginal-miner assumption (OBJECTIONS.md (b)). In
returns space, the only time-varying driver of modeled cost is network
difficulty (and any block-reward change), so the regression is effectively
"Qi returns vs difficulty returns". The constants DO matter for every
LEVEL claim - joules/Qi, the price-to-cost ratio, the Qi index, claim 2's
bundles - which is why the level sensitivity (price/cost ratio at $0.04,
base, and $0.20 per kWh) is reported separately below.
"""
from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from fetch_data import load_research_config, read_cache
from series import align_by_date, log_returns, ols, pearson


def joules_per_qi(*, difficulty: float, block_reward_qi: float, hashrate_hps: float, watts: float) -> float:
    if block_reward_qi <= 0 or hashrate_hps <= 0:
        return 0.0
    hashes_per_qi = difficulty / block_reward_qi
    seconds_per_qi = hashes_per_qi / hashrate_hps
    return seconds_per_qi * watts


def modeled_cost_usd_per_qi(*, difficulty: float, block_reward_qi: float, hashrate_hps: float, watts: float, usd_per_kwh: float) -> float:
    joules = joules_per_qi(
        difficulty=difficulty, block_reward_qi=block_reward_qi, hashrate_hps=hashrate_hps, watts=watts
    )
    return joules / 3_600_000.0 * usd_per_kwh


def cost_series(difficulty_series: dict[str, float], config: dict[str, Any]) -> dict[str, float]:
    gpu = config["reference_gpu"]
    network = config["network"]
    return {
        date: modeled_cost_usd_per_qi(
            difficulty=difficulty,
            block_reward_qi=float(Decimal(str(network["block_reward_qi"]))),
            hashrate_hps=float(gpu["hashrate_hps"]),
            watts=float(gpu["watts"]),
            usd_per_kwh=float(Decimal(str(network["usd_per_kwh"]))),
        )
        for date, difficulty in difficulty_series.items()
    }


def cost_level_sensitivity(
    qi: list[float],
    cost: list[float],
    config: dict[str, Any],
    kwh_scenarios: tuple[float, ...] = (0.04, 0.20),
) -> dict[str, Any]:
    """Median price-to-modeled-cost ratio under different $/kWh assumptions.

    Levels, not returns: the returns verdict is scale-invariant to $/kWh (it
    cancels in log-returns), so the global-marginal-miner assumption shows up
    only here - in how far above or below modeled production cost Qi trades.
    """
    ratios = sorted(p / c for p, c in zip(qi, cost) if c > 0)
    if not ratios:
        return {"available": False}
    n = len(ratios)
    base_ratio = ratios[n // 2] if n % 2 else (ratios[n // 2 - 1] + ratios[n // 2]) / 2
    base_kwh = float(Decimal(str(config["network"]["usd_per_kwh"])))
    scenarios = {f"{base_kwh:.2f}": round(base_ratio, 4)}
    for kwh in kwh_scenarios:
        if kwh > 0:
            scenarios[f"{kwh:.2f}"] = round(base_ratio * base_kwh / kwh, 4)
    return {
        "available": True,
        "median_price_to_cost_ratio_by_usd_per_kwh": dict(sorted(scenarios.items())),
        "note": "levels only; the returns-based verdict is invariant to $/kWh by construction",
    }


def liquidity_stats(volume_usd: dict[str, float] | None) -> dict[str, Any]:
    """Honest liquidity context: thin volume weakens any price-based conclusion."""
    if not volume_usd:
        return {"available": False, "note": "no volume series cached; liquidity unassessed"}
    values = sorted(volume_usd.values())
    n = len(values)
    median = values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2
    return {
        "available": True,
        "days": n,
        "median_daily_volume_usd": round(median, 2),
        "min_daily_volume_usd": round(values[0], 2),
        "max_daily_volume_usd": round(values[-1], 2),
    }


def analyze(
    *,
    qi_usd: dict[str, float],
    btc_usd: dict[str, float],
    difficulty: dict[str, float],
    config: dict[str, Any],
    qi_volume_usd: dict[str, float] | None = None,
    eth_usd: dict[str, float] | None = None,
) -> dict[str, Any]:
    cost_usd = cost_series(difficulty, config)
    eth: list[float] | None = None
    if eth_usd:
        dates, (qi, btc, cost, eth) = align_by_date(qi_usd, btc_usd, cost_usd, eth_usd)
    else:
        dates, (qi, btc, cost) = align_by_date(qi_usd, btc_usd, cost_usd)
    n = len(dates)
    min_samples = int(config.get("verdict", {}).get("min_samples", 90))

    qi_returns = log_returns(qi)
    cost_returns = log_returns(cost)

    energy_regression = ols(cost_returns, qi_returns)
    null_regressions: dict[str, dict[str, Any]] = {"BTC": ols(log_returns(btc), qi_returns)}
    if eth is not None:
        null_regressions["ETH"] = ols(log_returns(eth), qi_returns)

    result: dict[str, Any] = {
        "aligned_days": n,
        "date_range": [dates[0], dates[-1]] if dates else [],
        "levels_correlation_qi_vs_cost": round(pearson(qi, cost), 6),
        "levels_correlation_qi_vs_btc": round(pearson(qi, btc), 6),
        "returns_regression_qi_on_energy_cost": energy_regression,
        "returns_regression_qi_on_btc": null_regressions["BTC"],
        "null_regressions": null_regressions,
        "null_hypotheses": sorted(null_regressions),
        "min_samples_for_verdict": min_samples,
        "liquidity": liquidity_stats(qi_volume_usd),
        "cost_level_sensitivity": cost_level_sensitivity(qi, cost, config),
    }
    if eth is not None:
        result["returns_regression_qi_on_eth"] = null_regressions["ETH"]
        result["levels_correlation_qi_vs_eth"] = round(pearson(qi, eth), 6)
    min_volume = float(config.get("verdict", {}).get("min_median_daily_volume_usd", 50_000))
    liquidity = result["liquidity"]
    if n < min_samples:
        result["verdict"] = "insufficient_data"
        result["verdict_reason"] = (
            f"only {n} aligned daily observations; verdict requires {min_samples}. "
            "No conclusion is drawn from thin data."
        )
    elif liquidity.get("available") and liquidity["median_daily_volume_usd"] < min_volume:
        result["verdict"] = "below_liquidity_threshold"
        result["verdict_reason"] = (
            f"median daily Qi volume ${liquidity['median_daily_volume_usd']:,.0f} is below the "
            f"pre-registered ${min_volume:,.0f} threshold: the market price is treated as noise and "
            "no conclusion is drawn in either direction. The energy-money thesis is currently "
            "untestable at this liquidity - that is the finding."
        )
    else:
        strongest_null_name = max(null_regressions, key=lambda name: null_regressions[name]["r_squared"])
        strongest_null = null_regressions[strongest_null_name]
        if energy_regression["r_squared"] > strongest_null["r_squared"] and energy_regression["beta"] > 0:
            result["verdict"] = "supports_energy_thesis"
            result["verdict_reason"] = (
                f"energy-cost returns explain Qi returns (R2={energy_regression['r_squared']:.4f}) "
                f"better than every null does (strongest: {strongest_null_name}, "
                f"R2={strongest_null['r_squared']:.4f}), with positive beta."
            )
        else:
            result["verdict"] = "energy_thesis_not_supported"
            result["verdict_reason"] = (
                f"{strongest_null_name} returns (R2={strongest_null['r_squared']:.4f}) explain Qi at "
                f"least as well as energy-cost returns (R2={energy_regression['r_squared']:.4f}): "
                "Qi trades like crypto beta, not energy money, over this window."
            )
    result["series"] = {"dates": dates, "qi_usd": qi, "btc_usd": btc, "modeled_cost_usd": cost}
    if eth is not None:
        result["series"]["eth_usd"] = eth
    return result


def render_markdown(result: dict[str, Any], *, synthetic: bool) -> str:
    energy = result["returns_regression_qi_on_energy_cost"]
    nulls = result.get("null_regressions", {"BTC": result["returns_regression_qi_on_btc"]})
    lines = []
    if synthetic:
        lines += ["> **SYNTHETIC SAMPLE DATA - pipeline demonstration only, not a finding.**", ""]
    lines += [
        "# Claim 1: Peg Tracking (market level)",
        "",
        "Does Qi's **market price** track its modeled energy cost of production, or does it trade like "
        f"generic crypto beta (nulls: {', '.join(sorted(nulls))})?",
        "",
        "*Not under test:* Quai's protocol couples emission to difficulty by construction - that is "
        "mechanics, not evidence. This analysis tests the market layer only.",
        "",
        f"- Aligned daily observations: **{result['aligned_days']}** ({' to '.join(result['date_range']) if result['date_range'] else 'none'})",
        f"- Levels correlation, Qi vs modeled cost: **{result['levels_correlation_qi_vs_cost']}** (levels correlate trivially when both trend; the regression below uses returns)",
        f"- Levels correlation, Qi vs BTC: **{result['levels_correlation_qi_vs_btc']}**",
        "",
        "| Hypothesis (daily log-returns) | beta | t(beta) | R2 | n |",
        "| --- | --- | --- | --- | --- |",
        f"| Qi ~ modeled energy cost | {energy['beta']} | {energy['t_beta']} | {energy['r_squared']} | {energy['n']} |",
    ]
    for name in sorted(nulls):
        null = nulls[name]
        lines.append(
            f"| Qi ~ {name} (null hypothesis) | {null['beta']} | {null['t_beta']} | {null['r_squared']} | {null['n']} |"
        )
    lines += [
        "",
        f"## Verdict: `{result['verdict']}`",
        "",
        result["verdict_reason"],
        "",
    ]
    sensitivity = result.get("cost_level_sensitivity", {})
    if sensitivity.get("available"):
        ratios = sensitivity["median_price_to_cost_ratio_by_usd_per_kwh"]
        lines += [
            "## Cost-model constants: what they can and cannot affect",
            "",
            "The $/kWh and reference-rig constants cancel in log-returns, so the verdict above is "
            "**invariant to the global-marginal-miner assumption by construction** (in returns space the "
            "regression is effectively Qi vs difficulty). The assumption matters only for *level* claims - "
            "how far above or below modeled production cost Qi trades:",
            "",
            "| $/kWh assumed | median price / modeled cost |",
            "| --- | --- |",
        ]
        lines += [f"| {kwh} | {ratio}x |" for kwh, ratio in ratios.items()]
        lines += [""]
    liquidity = result.get("liquidity", {})
    if liquidity.get("available"):
        lines += [
            "## Liquidity context",
            "",
            f"Median daily Qi volume: ${liquidity['median_daily_volume_usd']:,.0f} "
            f"(min ${liquidity['min_daily_volume_usd']:,.0f}, max ${liquidity['max_daily_volume_usd']:,.0f}, "
            f"{liquidity['days']} days). Thin volume weakens any price-based conclusion in either "
            "direction; see OBJECTIONS.md.",
            "",
        ]
    else:
        lines += ["## Liquidity context", "", liquidity.get("note", ""), ""]
    return "\n".join(lines)


def render_chart(result: dict[str, Any], path: str, *, synthetic: bool) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    series = result["series"]
    dates = series["dates"]

    def normalize(values: list[float]) -> list[float]:
        base = next((v for v in values if v > 0), 1.0)
        return [v / base for v in values]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(dates, normalize(series["qi_usd"]), label="Qi market price (normalized)")
    ax.plot(dates, normalize(series["modeled_cost_usd"]), label="Modeled energy cost (normalized)")
    ax.plot(dates, normalize(series["btc_usd"]), label="BTC (normalized, null hypothesis)", alpha=0.6)
    if "eth_usd" in series:
        ax.plot(dates, normalize(series["eth_usd"]), label="ETH (normalized, null hypothesis)", alpha=0.6)
    step = max(len(dates) // 10, 1)
    ax.set_xticks(dates[::step])
    ax.tick_params(axis="x", rotation=45)
    title = "Claim 1: Qi price vs modeled energy cost of production"
    if synthetic:
        title += "  [SYNTHETIC SAMPLE DATA]"
    ax.set_title(title)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return True


def load_inputs(config: dict[str, Any], *, sample: bool) -> dict[str, dict[str, float]] | None:
    data_dir = Path("data/sample" if sample else config.get("data_dir", "data"))
    out = {}
    for name in ("qi_usd", "btc_usd", "difficulty"):
        cached = read_cache(data_dir, name)
        if cached is None:
            print(
                f"missing {data_dir}/{name}.json - run `python3 fetch_data.py` first"
                + ("" if sample else " (or use --sample to test the pipeline on synthetic data)")
            )
            return None
        out[name] = {date: float(value) for date, value in cached["series"].items()}
    for optional in ("qi_volume_usd", "eth_usd"):
        cached = read_cache(data_dir, optional)
        if cached is not None:
            out[optional] = {date: float(value) for date, value in cached["series"].items()}
        elif optional == "eth_usd":
            print("note: no eth_usd cache; running with BTC as the only null hypothesis")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Claim 1: peg tracking analysis")
    parser.add_argument("--config", default="research.yaml")
    parser.add_argument("--sample", action="store_true", help="Use synthetic sample fixtures (testing only)")
    args = parser.parse_args()
    config = load_research_config(args.config)
    inputs = load_inputs(config, sample=args.sample)
    if inputs is None:
        return 1
    result = analyze(
        qi_usd=inputs["qi_usd"],
        btc_usd=inputs["btc_usd"],
        difficulty=inputs["difficulty"],
        config=config,
        qi_volume_usd=inputs.get("qi_volume_usd"),
        eth_usd=inputs.get("eth_usd"),
    )
    results_dir = Path(config.get("results_dir", "results"))
    results_dir.mkdir(parents=True, exist_ok=True)
    stats = {key: value for key, value in result.items() if key != "series"}
    stats["synthetic"] = args.sample
    (results_dir / "claim1_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    markdown = render_markdown(result, synthetic=args.sample)
    (results_dir / "claim1.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    if render_chart(result, str(results_dir / "claim1_peg.png"), synthetic=args.sample):
        print(f"chart: {results_dir}/claim1_peg.png")
    else:
        print("matplotlib not installed; chart skipped (pip install matplotlib)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
