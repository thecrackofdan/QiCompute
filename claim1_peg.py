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

Cost model (single-algorithm baseline):
  difficulty (hashes/block) / block_reward (Qi/block) = hashes/Qi;
  divided by the reference GPU's hashrate gives seconds of work per Qi;
  times watts gives joules per Qi; times $/kWh gives modeled USD cost per Qi.

Multi-algorithm extension (TWP workshares):
  Under Quai's TWP (Tensor Work Proof) native merge-mining algorithm, GPUs
  running InferenceGemm submit Tensor Work Receipts as Quai workshares and
  earn Qi rewards. The GPU IS the miner; no ASIC hardware is required.

  When workshare data is available (fetch_data.py collects daily avg workshare
  count and per-algorithm difficulty from the RPC), the cost model is extended:
    total_effective_difficulty = kawpow_difficulty
                               + sum(ws_difficulty[algo] * ws_count[algo]
                                     * algo_energy_factor[algo])
  where algo_energy_factor normalises each algorithm's difficulty to the
  energy equivalent of KawPoW difficulty. For TWP, the energy_factor is
  calibrated via `benchmark.py --calibrate-rig --algo twp`.
  This gives an effective difficulty that feeds the same joules_per_qi formula.

  NOTE: The returns-based verdict remains invariant to the absolute energy
  scale ($/kWh, watts, hashrate all cancel in log-returns). The multi-
  algorithm extension only affects LEVEL claims (joules/Qi, price-to-cost
  ratio) and the completeness of the energy anchor story.

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


# ---------------------------------------------------------------------------
# Algorithm energy normalisation factors (J per hash, relative to KawPoW).
# These are used to convert workshare difficulty from SHA-256 / Scrypt into
# an energy-equivalent KawPoW difficulty for the multi-algorithm cost model.
#
# Derivation (approximate, from published ASIC specs):
#   KawPoW reference: RTX 3090, ~45 MH/s at 300 W -> 6.67e-9 J/hash
#   SHA-256 reference: Antminer S21, ~200 TH/s at 3500 W -> 1.75e-14 J/hash
#   Scrypt reference: Antminer L9, ~16 GH/s at 3360 W -> 2.10e-10 J/hash
#
# energy_factor[algo] = J_per_hash[algo] / J_per_hash[kawpow]
# So SHA-256 difficulty contributes much less energy per hash than KawPoW,
# but SHA-256 difficulty numbers are astronomically larger (Bitcoin-scale),
# so the product (difficulty * energy_factor) gives the energy-equivalent.
#
# These factors are stored in research.yaml under soap.algo_energy_factors
# and can be updated as better hardware benchmarks become available.
# The default values below are used when not present in config.
_DEFAULT_ALGO_ENERGY_FACTORS: dict[str, float] = {
    "kawpow": 1.0,
    "twp": 1.0,   # placeholder — calibrate with benchmark.py --calibrate-rig --algo twp
}


def algo_energy_factors(config: dict[str, Any]) -> dict[str, float]:
    """Return per-algorithm energy normalisation factors from config or defaults."""
    soap_cfg = config.get("soap", {})
    user_factors = soap_cfg.get("algo_energy_factors", {})
    return {**_DEFAULT_ALGO_ENERGY_FACTORS, **user_factors}


def effective_difficulty(
    kawpow_difficulty: float,
    workshare_difficulty: dict[str, float] | None,
    factors: dict[str, float],
) -> float:
    """Compute total energy-equivalent difficulty across all algorithms.

    kawpow_difficulty  : daily KawPoW block difficulty (hashes/block)
    workshare_difficulty: dict mapping algo name -> daily avg workshare
                          difficulty contribution for that algo.
                          Keys: 'twp' (TWP inference receipts), 'kawpow_ws'
                          (KawPoW workshares below block threshold).
                          None or empty -> single-algorithm baseline.
    factors            : energy normalisation factors from algo_energy_factors()

    Returns the effective difficulty to use in joules_per_qi(), expressed in
    KawPoW-equivalent hashes/block.
    """
    total = kawpow_difficulty
    if workshare_difficulty:
        for algo, ws_diff in workshare_difficulty.items():
            factor = factors.get(algo, 1.0)
            total += ws_diff * factor
    return total


def joules_per_qi(*, difficulty: float, block_reward_qi: float | str, hashrate_hps: float, watts: float) -> float:
    if hashrate_hps <= 0:
        return 0.0
    
    # If dynamic, use the protocol k_Qi formula:
    # reward_Qi = k_Qi * difficulty
    # baseKqi = 1 / (8 * 10^9)
    # k_Qi doubles every 2.69 years, but for now we use baseKqi
    if block_reward_qi == "dynamic":
        base_kqi = 1.0 / 8_000_000_000.0
        # hashes_per_qi = difficulty / reward_Qi = difficulty / (k_Qi * difficulty) = 1 / k_Qi
        hashes_per_qi = 1.0 / base_kqi
    else:
        reward = float(block_reward_qi)
        if reward <= 0:
            return 0.0
        hashes_per_qi = difficulty / reward
        
    seconds_per_qi = hashes_per_qi / hashrate_hps
    return seconds_per_qi * watts


def modeled_cost_usd_per_qi(*, difficulty: float, block_reward_qi: float | str, hashrate_hps: float, watts: float, usd_per_kwh: float) -> float:
    joules = joules_per_qi(
        difficulty=difficulty, block_reward_qi=block_reward_qi, hashrate_hps=hashrate_hps, watts=watts
    )
    return joules / 3_600_000.0 * usd_per_kwh


def cost_series(
    difficulty_series: dict[str, float],
    config: dict[str, Any],
    workshare_difficulty_series: dict[str, dict[str, float]] | None = None,
) -> dict[str, float]:
    """Build the daily modeled USD cost of producing one Qi.

    If workshare_difficulty_series is provided (keyed by date, values are
    per-algo difficulty dicts), the multi-algorithm effective difficulty is
    used. Otherwise falls back to the single-algorithm KawPoW baseline.
    """
    gpu = config["reference_gpu"]
    network = config["network"]
    factors = algo_energy_factors(config)
    result = {}
    for date, kawpow_diff in difficulty_series.items():
        ws_diff = workshare_difficulty_series.get(date) if workshare_difficulty_series else None
        eff_diff = effective_difficulty(kawpow_diff, ws_diff, factors)
        reward_cfg = network["block_reward_qi"]
        reward_val = reward_cfg if reward_cfg == "dynamic" else float(Decimal(str(reward_cfg)))
        result[date] = modeled_cost_usd_per_qi(
            difficulty=eff_diff,
            block_reward_qi=reward_val,
            hashrate_hps=float(gpu["hashrate_hps"]),
            watts=float(gpu["watts"]),
            usd_per_kwh=float(Decimal(str(network["usd_per_kwh"]))),
        )
    return result


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
    workshare_difficulty_series: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    cost_usd = cost_series(difficulty, config, workshare_difficulty_series)
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

    # Summarise which algorithms contributed to the energy model this run
    ws_algos_used: list[str] = []
    if workshare_difficulty_series:
        all_algos: set[str] = set()
        for ws_dict in workshare_difficulty_series.values():
            all_algos.update(ws_dict.keys())
        ws_algos_used = sorted(all_algos)

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
        "thresholds_frozen": bool(config.get("verdict", {}).get("thresholds_frozen", False)),
        "liquidity": liquidity_stats(qi_volume_usd),
        "cost_level_sensitivity": cost_level_sensitivity(qi, cost, config),
        "multi_algo_energy": {
            "enabled": bool(workshare_difficulty_series),
            "algorithms": ws_algos_used,
            "note": (
                "Multi-algorithm effective difficulty used (KawPoW + workshare contributions). "
                f"Algorithms: {', '.join(ws_algos_used)}. "
                "Returns verdict is invariant to this; level claims (joules/Qi, price/cost) are affected."
            ) if ws_algos_used else (
                "Single-algorithm KawPoW baseline used. "
                "Workshare difficulty data not available; run fetch_data.py to collect it. "
                "The energy anchor is an undercount until SOAP workshare data is included."
            ),
        },
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
        # Pre-registered thresholds from PREDICTIONS.md (enforced only when frozen):
        # - R2(energy) > max(R2 of every null)
        # - energy beta in [0.5, 1.5]
        # - t-statistic of energy beta > 2
        verdict_cfg = config.get("verdict", {})
        beta_min = float(verdict_cfg.get("beta_min", 0.5))
        beta_max = float(verdict_cfg.get("beta_max", 1.5))
        t_min = float(verdict_cfg.get("t_beta_min", 2.0))
        e_beta = energy_regression["beta"]
        e_r2 = energy_regression["r_squared"]
        e_t = energy_regression["t_beta"]
        r2_beats_nulls = e_r2 > strongest_null["r_squared"]
        beta_in_range = beta_min <= e_beta <= beta_max
        t_significant = e_t > t_min
        if r2_beats_nulls and beta_in_range and t_significant:
            result["verdict"] = "supports_energy_thesis"
            result["verdict_reason"] = (
                f"energy-cost returns explain Qi returns (R2={e_r2:.4f}) "
                f"better than every null does (strongest: {strongest_null_name}, "
                f"R2={strongest_null['r_squared']:.4f}), with beta={e_beta:.4f} "
                f"in [{beta_min}, {beta_max}] and t={e_t:.2f} > {t_min}."
            )
        else:
            # Build a specific failure reason to aid diagnosis
            failures = []
            if not r2_beats_nulls:
                failures.append(
                    f"{strongest_null_name} R2={strongest_null['r_squared']:.4f} "
                    f">= energy R2={e_r2:.4f}"
                )
            if not beta_in_range:
                failures.append(
                    f"beta={e_beta:.4f} outside pre-registered range [{beta_min}, {beta_max}]"
                )
            if not t_significant:
                failures.append(
                    f"t={e_t:.2f} <= pre-registered threshold {t_min}"
                )
            result["verdict"] = "energy_thesis_not_supported"
            result["verdict_reason"] = (
                f"{strongest_null_name} returns (R2={strongest_null['r_squared']:.4f}) "
                f"explain Qi at least as well as energy-cost returns (R2={e_r2:.4f}). "
                "Pre-registered failure condition(s) met: " + "; ".join(failures) + ". "
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
    if not result.get("thresholds_frozen", False):
        lines += [
            "> **THRESHOLDS DRAFT - not citable.** PREDICTIONS.md candidates are not yet frozen "
            "(`verdict.thresholds_frozen: false` in research.yaml). Freeze them - before looking at "
            "real regression output - and rerun before citing any verdict.",
            "",
        ]
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
    multi_algo = result.get("multi_algo_energy", {})
    if multi_algo:
        lines += [
            "## Multi-algorithm energy model (SOAP / workshares)",
            "",
            multi_algo.get("note", ""),
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


def load_workshare_difficulty_series(
    data_dir: Path,
) -> dict[str, dict[str, float]] | None:
    """Load per-algo workshare difficulty from cached JSON files.

    Returns a dict keyed by date -> {algo: difficulty_contribution} or None
    if no workshare data is available.
    """
    # Each algo's workshare difficulty is stored as a separate cache file:
    #   workshare_difficulty_sha256.json, workshare_difficulty_scrypt.json,
    #   workshare_difficulty_kawpow_ws.json
    algo_map = {
        "sha256": "workshare_difficulty_sha256",
        "scrypt": "workshare_difficulty_scrypt",
        "kawpow_ws": "workshare_difficulty_kawpow_ws",
    }
    combined: dict[str, dict[str, float]] = {}
    found_any = False
    for algo, cache_name in algo_map.items():
        cached = read_cache(data_dir, cache_name)
        if cached is None:
            continue
        found_any = True
        for date, value in cached["series"].items():
            combined.setdefault(date, {})[algo] = float(value)
    return combined if found_any else None


def load_inputs(config: dict[str, Any], *, sample: bool) -> dict[str, Any] | None:
    data_dir = Path("data/sample" if sample else config.get("data_dir", "data"))
    out: dict[str, Any] = {}
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
    # Multi-algorithm workshare difficulty (optional, SOAP data)
    ws_diff = load_workshare_difficulty_series(data_dir)
    if ws_diff:
        out["workshare_difficulty_series"] = ws_diff
        print(f"note: workshare difficulty loaded for {len(ws_diff)} days; multi-algorithm energy model active")
    else:
        print("note: no workshare difficulty cache; using single-algorithm KawPoW baseline")
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
        workshare_difficulty_series=inputs.get("workshare_difficulty_series"),
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
