from __future__ import annotations

from dataclasses import dataclass


DEMAND_LEVELS = ("low", "normal", "high", "burst")


@dataclass(frozen=True)
class MarketDemand:
    demand_level: str
    queued_jobs: int
    waiting_customers: int
    expected_inference_revenue: float
    average_queue_latency: float
    utilization_pressure: float

    def to_dict(self) -> dict[str, float | int | str]:
        return {
            "demand_level": self.demand_level,
            "queued_jobs": self.queued_jobs,
            "waiting_customers": self.waiting_customers,
            "expected_inference_revenue": self.expected_inference_revenue,
            "average_queue_latency": self.average_queue_latency,
            "utilization_pressure": self.utilization_pressure,
        }


@dataclass(frozen=True)
class InferenceOpportunity:
    expected_qi_per_hour: float
    expected_cost_per_hour: float
    expected_profit_per_hour: float
    utilization_pressure: float

    def to_dict(self) -> dict[str, float]:
        return {
            "expected_qi_per_hour": self.expected_qi_per_hour,
            "expected_cost_per_hour": self.expected_cost_per_hour,
            "expected_profit_per_hour": self.expected_profit_per_hour,
            "utilization_pressure": self.utilization_pressure,
        }


def estimate_market_demand(
    *,
    queued_jobs: int,
    waiting_customers: int,
    expected_inference_revenue: float,
    average_queue_latency: float,
    active_workers: int,
) -> MarketDemand:
    queued_jobs = max(int(queued_jobs), 0)
    waiting_customers = max(int(waiting_customers), 0)
    active_workers = max(int(active_workers), 1)
    utilization_pressure = min(1.0, queued_jobs / active_workers)
    if queued_jobs >= active_workers * 4 or average_queue_latency >= 120:
        level = "burst"
    elif queued_jobs >= active_workers * 2 or average_queue_latency >= 60:
        level = "high"
    elif queued_jobs > 0 or waiting_customers > 0:
        level = "normal"
    else:
        level = "low"
    return MarketDemand(
        demand_level=level,
        queued_jobs=queued_jobs,
        waiting_customers=waiting_customers,
        expected_inference_revenue=round(max(float(expected_inference_revenue), 0.0), 12),
        average_queue_latency=round(max(float(average_queue_latency), 0.0), 6),
        utilization_pressure=round(utilization_pressure, 6),
    )


def estimate_inference_opportunity(
    demand: MarketDemand,
    *,
    worker_count: int,
    energy_cost_per_hour: float,
    max_jobs_per_worker_hour: float = 1.0,
) -> InferenceOpportunity:
    capacity = max(int(worker_count), 0) * max(float(max_jobs_per_worker_hour), 0.0)
    served_jobs = min(float(demand.queued_jobs), capacity)
    revenue_per_job = demand.expected_inference_revenue / demand.queued_jobs if demand.queued_jobs else 0.0
    revenue = served_jobs * revenue_per_job
    cost = max(float(energy_cost_per_hour), 0.0) * max(int(worker_count), 0) * demand.utilization_pressure
    return InferenceOpportunity(
        expected_qi_per_hour=round(revenue, 12),
        expected_cost_per_hour=round(cost, 12),
        expected_profit_per_hour=round(revenue - cost, 12),
        utilization_pressure=demand.utilization_pressure,
    )
