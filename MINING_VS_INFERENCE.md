# Mining vs Inference Thesis

## Core Question

Useful compute outperforms mining when verified inference revenue, after energy, overhead, and failure risk, exceeds the expected profit from mining on the same hardware.

```text
serve inference if:
expected inference revenue - inference costs - verification/failure risk
>
expected mining revenue - mining energy cost
```

## Crossover Assumptions

- Mining profitability can be estimated per GPU per hour.
- Inference revenue can be estimated per job, token, latency class, privacy class, and verification class.
- Workers can switch between mining and inference with low enough friction.
- Customers create enough demand to keep workers utilized.
- Marketplace fees, verification overhead, and failed jobs do not erase inference margins.
- Workers trust settlement enough to prefer inference over mining.

## Strongest Parts Of The Thesis

- Mining fallback creates a clean reservation price. Workers have a reason to ask for inference prices above mining profit.
- Useful work does not mint Qi. This keeps issuance simple and avoids rewarding fake useful work with new currency.
- Idle hardware has an economically meaningful default path.
- The crossover metric is testable with real hardware and real job pricing.

## Weakest Parts Of The Thesis

- Mining profitability is not measured against real Qi network conditions in this repo.
- Inference demand is simulated, not observed.
- Customer willingness to pay a privacy or verification premium is unvalidated.
- Switching costs between mining and inference are not measured.
- Verification overhead is simplified.
- Hardware depreciation and model availability are not included in the current economics.

## Missing Measurements

- GPU-specific mining yield and energy draw.
- GPU-specific inference throughput by model.
- End-to-end job latency and failure rate.
- Verification overhead per job.
- Real power prices by region/operator.
- Worker idle time and utilization under realistic demand.
- Customer price elasticity.
- Marketplace fee tolerance.

## Required Real-World Data

1. A hardware matrix covering common GPUs, model sizes, tokens per second, watts, and thermal limits.
2. Mining fallback data for authorized Qi mining under realistic difficulty.
3. Paid or simulated customer demand with actual job size distributions.
4. Operator cost data: electricity, hardware depreciation, maintenance, bandwidth, and setup time.
5. Verification accuracy and overhead under honest, flaky, and malicious workers.

## Current Conclusion

The thesis is plausible but not validated. The cleanest research target is the crossover threshold: find the demand and price level where a known GPU earns more by serving verified inference than by mining.
