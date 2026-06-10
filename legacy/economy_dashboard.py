from __future__ import annotations

import argparse
from typing import Any

from agent_competition import run_agent_competition
from crossover import analyze_mining_inference_crossover
from customer_demand import choose_customer_provider
from market_pricing import compute_market_price
from monetary_simulation import run_monetary_simulation
from regional_market import simulate_regional_market


def run_economy_dashboard(cycles: int = 100) -> dict[str, Any]:
    customer_choice = choose_customer_provider(
        "privacy_sensitive",
        {
            "QiCompute": {
                "price": 0.08,
                "latency": 180,
                "privacy_score": 0.94,
                "reliability": 0.88,
                "verification_score": 0.92,
                "region_match": 0.9,
            },
            "centralized_ai_api": {
                "price": 0.06,
                "latency": 95,
                "privacy_score": 0.45,
                "reliability": 0.96,
                "verification_score": 0.35,
                "region_match": 0.65,
            },
            "gpu_cloud": {
                "price": 0.075,
                "latency": 220,
                "privacy_score": 0.60,
                "reliability": 0.85,
                "verification_score": 0.45,
                "region_match": 0.5,
            },
            "self_hosted": {
                "price": 0.12,
                "latency": 260,
                "privacy_score": 0.98,
                "reliability": 0.72,
                "verification_score": 0.55,
                "region_match": 1.0,
            },
        },
    )
    price = compute_market_price(
        compute_supply=8,
        customer_demand=14,
        worker_utilization=0.82,
        mining_fallback_profitability=0.04,
        latency_class="low_latency",
        privacy_class="private",
        verification_class="verified",
        regional_scarcity=0.3,
    )
    crossover = analyze_mining_inference_crossover(
        mining_qi_per_hour=price.floor_price_qi,
        inference_qi_per_job=price.spot_price_qi,
        jobs_per_hour_capacity=4,
        current_inference_demand=3,
    )
    competition = run_agent_competition(cycles)
    regional = simulate_regional_market(cycles)
    monetary = run_monetary_simulation(cycles)
    return {
        "customer_choice_summary": {
            "chosen_provider": customer_choice.chosen_provider,
            "reason": customer_choice.reason,
            "willingness_to_pay_qi": customer_choice.willingness_to_pay_qi,
        },
        "pricing_crossover_summary": {
            "spot_price_qi": price.spot_price_qi,
            "floor_price_qi": price.floor_price_qi,
            "preferred_action": crossover.preferred_action,
            "crossover_threshold": crossover.crossover_threshold,
        },
        "agent_competition_summary": {
            "survival_rate": competition["survival_rate"],
            "top_strategy": max(
                competition["strategies"].items(),
                key=lambda item: item[1]["final_qi_balance"],
            )[0],
        },
        "regional_routing_summary": {
            "regional_job_volume": regional["regional_job_volume"],
            "cross_region_routing_rate": regional["cross_region_routing_rate"],
        },
        "monetary_circulation_summary": {
            "qi_issued": monetary["qi_issued"],
            "qi_circulated": monetary["qi_circulated"],
            "velocity_estimate": monetary["velocity_estimate"],
            "demand_vs_issuance_ratio": monetary["demand_vs_issuance_ratio"],
        },
        "top_risks": _top_risks(monetary, regional),
        "best_opportunities": _best_opportunities(customer_choice.chosen_provider, crossover.preferred_action),
    }


def _top_risks(monetary: dict[str, Any], regional: dict[str, Any]) -> list[str]:
    risks = []
    if monetary["qi_hoarded"] > monetary["qi_circulated"]:
        risks.append("Qi hoarding exceeds circulation")
    if regional["cross_region_routing_rate"] > 0.25:
        risks.append("Regional supply is uneven")
    if not risks:
        risks.append("Demand shocks remain the main simulation risk")
    return risks


def _best_opportunities(provider: str, preferred_action: str) -> list[str]:
    opportunities = []
    if provider == "QiCompute":
        opportunities.append("Privacy-sensitive customers can prefer verified local compute")
    if preferred_action == "serve_inference":
        opportunities.append("Inference demand clears the mining fallback floor")
    opportunities.append("Agent-to-agent trade can reuse the same Qi settlement layer")
    return opportunities


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic QiCompute economy dashboard")
    parser.add_argument("--cycles", type=int, default=100)
    args = parser.parse_args()
    dashboard = run_economy_dashboard(args.cycles)
    for section, values in dashboard.items():
        print(f"{section}: {values}")


if __name__ == "__main__":
    main()
