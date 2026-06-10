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

## Configuration

```yaml
energy_anchor:
  enabled: true
  reference_mining_qi_per_hour: 0.05
  reference_power_watts: 250
  worker_share: 0.85
  overhead_multiplier: 1.2
```

Set `enabled: false` to fall back to the static `pricing.energy_rate_qi_per_joule` value (default 0.0, which disables the energy pricing component entirely).

## CLI

```bash
make energy-report
python3 energy_anchor.py --mining-qi-per-hour 0.05 --power-watts 250 --job-energy-joules 750 --job-token-price-qi 0.0001
```

Prints the parity rate and an anchored price for a sample job as JSON.

## Current Evidence

Supported claims:

- The parity rate, anchored prices, derived pricing rates, and epoch energy reports are deterministic and covered by tests.
- Energy flows end-to-end in the prototype: telemetry watts -> receipt joules -> epoch totals -> settled Qi per joule.

Unsupported claims:

- The reference mining rate (`reference_mining_qi_per_hour`) reflects real Qi mining yield. It is a configured assumption, not a measurement.
- Telemetry joules approximate true wall-socket energy. `nvidia-smi` power draw excludes CPU, memory, cooling, and PSU losses, and the 250W fallback is a constant.
- Customers will accept energy-denominated pricing.

Unknowns:

- Real joules-per-token on actual hardware and realistic workloads (see `RESEARCH_ROADMAP.md`).
- How the parity rate should respond to mining difficulty changes over time.
- Whether a single global reference rig is adequate, or whether the anchor must be regional (energy costs and hardware vary by region).

## Limitations

This is a local deterministic model, not an oracle. There is no live mining feed, no real energy metering, and no production price discovery. The anchor makes the qi-equals-energy assumption inspectable and testable; it does not validate it.
