"""Claim 1: does Qi's market price track its modeled energy cost of production?

    python3 claim1_peg.py              # analyze cached real data (data/)
    python3 claim1_peg.py --sample     # SYNTHETIC fixtures, for testing the pipeline only

The null hypothesis is built in: Qi daily log-returns are regressed both on
the modeled cost-of-production returns and on BTC returns. If BTC beta
explains Qi better than energy cost does, the verdict says the thesis is not
supported. Below verdict.min_samples aligned observations the verdict is
"insufficient_data" - thin data is never smoothed into a conclusion.

Cost model: difficulty (hashes/block) / block_reward (Qi/block) = hashes/Qi;
divided by the reference GPU's hashrate gives seconds of work per Qi; times
watts gives joules per Qi; times $/kWh gives modeled USD cost per Qi.
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
) -> dict[str, Any]:
    cost_usd = cost_series(difficulty, config)
    dates, (qi, btc, cost) = align_by_date(qi_usd, btc_usd, cost_usd)
    n = len(dates)
    min_samples = int(config.get("verdict", {}).get("min_samples", 90))

    qi_returns = log_returns(qi)
    cost_returns = log_returns(cost)
    btc_returns = log_returns(btc)

    energy_regression = ols(cost_returns, qi_returns)
    btc_regression = ols(btc_returns, qi_returns)

    result: dict[str, Any] = {
        "aligned_days": n,
        "date_range": [dates[0], dates[-1]] if dates else [],
        "levels_correlation_qi_vs_cost": round(pearson(qi, cost), 6),
        "levels_correlation_qi_vs_btc": round(pearson(qi, btc), 6),
        "returns_regression_qi_on_energy_cost": energy_regression,
        "returns_regression_qi_on_btc": btc_regression,
        "min_samples_for_verdict": min_samples,
        "liquidity": liquidity_stats(qi_volume_usd),
    }
    if n < min_samples:
        result["verdict"] = "insufficient_data"
        result["verdict_reason"] = (
            f"only {n} aligned daily observations; verdict requires {min_samples}. "
            "No conclusion is drawn from thin data."
        )
    elif (
        energy_regression["r_squared"] > btc_regression["r_squared"]
        and energy_regression["beta"] > 0
    ):
        result["verdict"] = "supports_energy_thesis"
        result["verdict_reason"] = (
            f"energy-cost returns explain Qi returns (R2={energy_regression['r_squared']:.4f}) "
            f"better than BTC returns do (R2={btc_regression['r_squared']:.4f}), with positive beta."
        )
    else:
        result["verdict"] = "energy_thesis_not_supported"
        result["verdict_reason"] = (
            f"BTC returns (R2={btc_regression['r_squared']:.4f}) explain Qi at least as well as "
            f"energy-cost returns (R2={energy_regression['r_squared']:.4f}): Qi trades like "
            "crypto beta, not energy money, over this window."
        )
    result["series"] = {"dates": dates, "qi_usd": qi, "btc_usd": btc, "modeled_cost_usd": cost}
    return result


def render_markdown(result: dict[str, Any], *, synthetic: bool) -> str:
    energy = result["returns_regression_qi_on_energy_cost"]
    btc = result["returns_regression_qi_on_btc"]
    lines = []
    if synthetic:
        lines += ["> **SYNTHETIC SAMPLE DATA - pipeline demonstration only, not a finding.**", ""]
    lines += [
        "# Claim 1: Peg Tracking",
        "",
        "Does Qi's market price track its modeled energy cost of production, or does it trade like BTC beta?",
        "",
        f"- Aligned daily observations: **{result['aligned_days']}** ({' to '.join(result['date_range']) if result['date_range'] else 'none'})",
        f"- Levels correlation, Qi vs modeled cost: **{result['levels_correlation_qi_vs_cost']}** (levels correlate trivially when both trend; the regression below uses returns)",
        f"- Levels correlation, Qi vs BTC: **{result['levels_correlation_qi_vs_btc']}**",
        "",
        "| Hypothesis (daily log-returns) | beta | t(beta) | R2 | n |",
        "| --- | --- | --- | --- | --- |",
        f"| Qi ~ modeled energy cost | {energy['beta']} | {energy['t_beta']} | {energy['r_squared']} | {energy['n']} |",
        f"| Qi ~ BTC (null hypothesis) | {btc['beta']} | {btc['t_beta']} | {btc['r_squared']} | {btc['n']} |",
        "",
        f"## Verdict: `{result['verdict']}`",
        "",
        result["verdict_reason"],
        "",
    ]
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
    volume = read_cache(data_dir, "qi_volume_usd")
    if volume is not None:
        out["qi_volume_usd"] = {date: float(value) for date, value in volume["series"].items()}
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
