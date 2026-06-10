# QiCompute Energy Model

## Core Idea

Qi is reflective of energy, and so is inference. Mining is the only issuance path, so every Qi enters circulation by burning a measurable number of joules. That makes the energy price of Qi observable: a reference rig's Qi minted per hour divided by its joules burned per hour is a Qi-per-joule exchange rate. Inference jobs are also measured in joules (telemetry watts times duration, recorded on every receipt), so the marketplace can price useful work against the same energy unit that issues the currency.

`energy_anchor.py` implements this layer.

## The Anchor

```
qi_per_joule = mining_qi_per_hour / (power_watts * 3600)
```

`mining_energy_parity` computes this rate from a reference mining rig. It is the reservation rate in energy terms: a joule spent on inference should settle at least as much Qi as the same joule would have minted through mining, or a rational worker mines instead. This restates the mining-fallback floor from `MINING_VS_INFERENCE.md` in Qi-per-joule rather than Qi-per-hour.

## Energy-Anchored Pricing

`energy_anchored_price` prices a job from its measured joules:

```
anchored_price_qi = energy_joules * qi_per_joule * overhead_multiplier
```

The overhead multiplier covers verification, routing, and operator margin. The function also reports `premium_over_energy_parity`, the ratio of the token-based quote to the anchored price. Above 1.0, inference pays more Qi per joule than mining issues, which is the rational condition for serving jobs.

## Wiring

- `pricing.estimate_job_price` resolves its energy rate through `derive_energy_rate(config)`. When the `energy_anchor` config section is enabled, the rate is derived from the reference rig (scaled by `worker_share`) instead of the static `pricing.energy_rate_qi_per_joule` value, so the energy component of job prices tracks the mining parity rate.
- `epochs.finalize_epoch` records `settled_qi_per_joule` in each epoch's `energy_totals` metadata: how much Qi the epoch actually settled per verified joule.
- `epoch_energy_report` compares an epoch's settled Qi-per-joule against the mining parity rate and emits an `energy_verdict` (`inference_beats_mining_parity` or `mining_parity_beats_inference`). This is the mining-versus-inference crossover question asked in energy units.

## Stability: Pricing Work, Not Speculation

Qi should behave like an energy-backed unit of account for useful work, not a volatile token. `energy_peg.py` adds three mechanisms on top of the anchor, each attacking one source of volatility:

### 1. Energy-denominated quotes

`quote_job_in_energy` prices a job in joules: measured energy times overhead and service-class multipliers. The joule price is invariant to Qi volatility by construction. Qi enters only at settlement, when the joule price converts at the smoothed parity rate. Token swings change the conversion, never the energy price of the work — the same way a contract priced in kWh is unaffected by currency moves until payment.

### 2. The smoothed parity oracle

A raw parity rate would reprice the marketplace instantly on every mining difficulty shock or thin-volume settlement epoch. `update_parity_oracle` publishes an exponential moving average of observed Qi-per-joule rates instead, and clamps any single update to `max_step_ratio` (default 10%) relative to the previous rate — the same damping idea as a difficulty adjustment clamp. `oracle_from_epoch_summaries` replays finalized epochs' `settled_qi_per_joule` into the oracle, so the published rate is reproducible from settlement history.

### 3. The stability corridor

`apply_stability_corridor` bounds spot prices inside `[floor, floor * corridor_ceiling_multiplier]`, where the floor is the energy reservation price (mining fallback). Demand surges raise prices within a known band instead of without limit; the report records how much premium was shed by the ceiling.

### 4. Standardized energy billing

Billing a worker's *measured* joules would be cost-plus pricing: a wasteful rig bills more than an efficient one for the same output, which rewards burning energy. `energy_standards.py` bills **reference joules** instead: each model class has a benchmark joules-per-token (`energy_anchor.reference_joules_per_token`), and a job's price is its output tokens times that benchmark — the same quote for every worker, the way electricity markets settle delivered power rather than fuel burned.

A worker's measured draw against the benchmark becomes their margin, not their billing basis: `efficiency_margin` and `worker_efficiency_report` (driven by the per-worker `average_energy_per_token` the database already tracks) report the premium an operator earns by beating the benchmark or the penalty for missing it. `recalibrate_reference` drifts the benchmark toward observed fleet efficiency with the same EMA-plus-clamp damping as the oracle, so hardware improvements eventually reach customers as lower prices while workers keep a near-term incentive to beat the current benchmark.

### Measured result

`simulate_peg_stability` (run via `make stability-report`) drives both pricing modes through the same deterministic boom/bust pattern in the observed Qi-per-joule rate. With defaults: raw token pricing has a coefficient of variation of 0.35 and a worst single-period jump of 161% (verdict: volatile); energy-pegged pricing has a coefficient of variation of 0.098 with the worst step bounded at the 10% clamp (verdict: stable) — a 72% volatility reduction, while the joule price never moves at all. `price_stability_report` provides the volatility metrics and verdict for any rate series.

## Configuration

```yaml
energy_anchor:
  enabled: true
  reference_mining_qi_per_hour: 0.05
  reference_power_watts: 250
  worker_share: 0.85
  overhead_multiplier: 1.2
  smoothing_alpha: 0.2
  max_step_ratio: 0.1
  corridor_ceiling_multiplier: 1.5
  stable_cv_threshold: 0.15
  reference_joules_per_token:
    default: 3.0
    llama-3.1-8b: 3.0
```

Set `enabled: false` to fall back to the static `pricing.energy_rate_qi_per_joule` value (default 0.0, which disables the energy pricing component entirely). `smoothing_alpha` through `stable_cv_threshold` configure the stability layer (`peg_settings` reads them with these defaults); `reference_joules_per_token` is the per-model billing benchmark table used by standardized billing.

## CLI

```bash
make energy-report
python3 energy_anchor.py --mining-qi-per-hour 0.05 --power-watts 250 --job-energy-joules 750 --job-token-price-qi 0.0001

make stability-report
python3 energy_peg.py --cycles 60 --smoothing-alpha 0.2 --max-step-ratio 0.1

make efficiency-report
python3 energy_standards.py --output-tokens 500 --measured-joules-per-token 2.4
```

`energy-report` prints the parity rate and an anchored price for a sample job. `stability-report` prints the raw-versus-pegged volatility comparison. `efficiency-report` prints a standardized quote and the efficiency margin for a sample worker.

## Current Evidence

Supported claims:

- The parity rate, anchored prices, derived pricing rates, and epoch energy reports are deterministic and covered by tests.
- Energy flows end-to-end in the prototype: telemetry watts -> receipt joules -> epoch totals -> settled Qi per joule.
- Under the modeled boom/bust rate pattern, energy-pegged quoting with the smoothed oracle reduces Qi cost volatility by more than 70% versus raw token pricing, with single-period moves bounded by the configured clamp (deterministic simulation, covered by tests).

Unsupported claims:

- The reference mining rate (`reference_mining_qi_per_hour`) reflects real Qi mining yield. It is a configured assumption, not a measurement.
- Telemetry joules approximate true wall-socket energy. `nvidia-smi` power draw excludes CPU, memory, cooling, and PSU losses, and the 250W fallback is a constant.
- Customers will accept energy-denominated pricing.
- The simulated boom/bust rate pattern resembles real Qi volatility. The 70%+ reduction is a property of the damping mechanism under that synthetic pattern, not a market measurement.
- The corridor ceiling will not starve supply. Capping demand premiums during real scarcity may push workers back to mining exactly when capacity is most needed; the right ceiling is an open tuning question.
- The 3.0 joules-per-token benchmark resembles real model energy use. It is a configured placeholder; real benchmarks require the hardware measurements in `RESEARCH_ROADMAP.md`.

Unknowns:

- Real joules-per-token on actual hardware and realistic workloads (see `RESEARCH_ROADMAP.md`).
- How the parity rate should respond to mining difficulty changes over time.
- Whether a single global reference rig is adequate, or whether the anchor must be regional (energy costs and hardware vary by region).
- The right smoothing alpha and step clamp for real settlement cadence: too much damping makes the oracle lag genuine cost shifts and misprice work; too little readmits the volatility it exists to remove.
- Whether an adversary can steer the oracle by feeding it thin or manufactured settlement epochs (oracle manipulation resistance is unmodeled).
- How benchmark recalibration should be governed: who measures fleet efficiency, how workers prove their reported draw, and whether per-model benchmarks fragment as model variants multiply.

## Limitations

This is a local deterministic model, not an oracle. There is no live mining feed, no real energy metering, and no production price discovery. The anchor makes the qi-equals-energy assumption inspectable and testable; it does not validate it.
