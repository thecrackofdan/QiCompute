from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CrossoverAnalysis:
    mining_revenue: float
    inference_revenue: float
    crossover_threshold: float
    utilization_threshold: float
    preferred_action: str

    def to_dict(self) -> dict[str, float | str]:
        return {
            "mining_revenue": self.mining_revenue,
            "inference_revenue": self.inference_revenue,
            "crossover_threshold": self.crossover_threshold,
            "utilization_threshold": self.utilization_threshold,
            "preferred_action": self.preferred_action,
        }


def analyze_mining_inference_crossover(
    *,
    mining_qi_per_hour: float,
    inference_qi_per_job: float,
    jobs_per_hour_capacity: float,
    current_inference_demand: float,
) -> CrossoverAnalysis:
    capacity = max(float(jobs_per_hour_capacity), 0.000000001)
    revenue_per_job = max(float(inference_qi_per_job), 0.0)
    mining = max(float(mining_qi_per_hour), 0.0)
    threshold_jobs = mining / revenue_per_job if revenue_per_job else float("inf")
    utilization_threshold = min(threshold_jobs / capacity, 1.0) if threshold_jobs != float("inf") else 1.0
    served_jobs = min(max(float(current_inference_demand), 0.0), capacity)
    inference = served_jobs * revenue_per_job
    return CrossoverAnalysis(
        mining_revenue=round(mining, 12),
        inference_revenue=round(inference, 12),
        crossover_threshold=round(threshold_jobs, 12) if threshold_jobs != float("inf") else threshold_jobs,
        utilization_threshold=round(utilization_threshold, 12),
        preferred_action="serve_inference" if inference > mining else "mine",
    )
