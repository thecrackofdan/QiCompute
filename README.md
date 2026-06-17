# QiCompute

An empirical research toolkit that tests whether **Qi** — the energy-denominated token of Quai Network — can function as a natural unit of account for AI inference compute. It measures the physics, runs the regressions, and delivers a reproducible verdict.

---

## What it does

QiCompute pulls live on-chain and market data, runs five falsifiable claims against it, and writes a full report to `results/REPORT.md`. Every number is traceable back to a cached data file; every verdict has a pre-registered failure condition.

The five claims, in order of dependency:

| # | Claim | Script | What it tests |
|---|---|---|---|
| 1 | **Peg tracking** | `claim1_peg.py` | Does Qi's market price track its modeled energy cost of production, beating BTC and ETH as null hypotheses? |
| 2 | **Unit-of-account stability** | `claim2_stability.py` | Is compute energy more stably priced in Qi than in USD or BTC? (Rolling 30-day volatility comparison) |
| 3 | **Joules/token ground truth** | `benchmark.py` | Measured tokens/sec, watts, and joules/token on real hardware, stored in a public-dataset SQLite schema |
| 4 | **Settlement** | `claim4_settlement.py` | Escrow → settle → refund cycle in micro-Qi, conservation-checked and receipt-emitting |
| 5 | **K-Quai controller** | `claim5_token_choice.py` | Does the on-chain QUAI↔Qi exchange rate respond to miner token preference as the monetary theory predicts? |

---

## Quick start

```bash
pip install -r requirements.txt

# Full pipeline: fetch live data, run all five claims, write results/REPORT.md
python3 reproduce.py

# Offline demo with synthetic data (labeled, not findings)
python3 reproduce.py --sample

# Run the test suite (33 deterministic tests)
python3 -m unittest
```

---

## How it works

### Data pipeline (`fetch_data.py`)

Fetches and caches everything to `data/` as JSON (with provenance and timestamp) plus a CSV mirror. Analysis only ever reads the cache — no live data during claim evaluation.

| Dataset | Source | Notes |
|---|---|---|
| Qi, BTC, ETH prices + volume | CoinGecko | Volume feeds the liquidity gate in claim 1 |
| Quai block difficulty | Quai JSON-RPC / explorer fallback | Incremental scan; resumes from last cached block |
| Miner token choice (`qi_fraction`) | Quai JSON-RPC `woHeader.lock` | Fraction of blocks where miner elected Qi reward |
| On-chain QUAI↔Qi exchange rate | Quai JSON-RPC `header.exchangeRate` | K-Quai controller rate; same scan pass as token choice |
| Workshare difficulty (KawPoW + SOAP) | Quai JSON-RPC `workshares` array | Split into `kawpow_ws` and `soap_ws` by `mixHash` heuristic |
| Electricity (USD/kWh) | EIA v2 API | Optional; flat fallback used and labeled if key absent |

### Claim 1 — Peg tracking

Converts Quai network difficulty into a modeled energy cost of producing one Qi, using a configurable reference rig (default: RTX 3090, 45 MH/s, 300 W) and electricity price. Since Project SOAP (Dec 2025), SHA-256 and Scrypt ASIC workshares are included in the energy model via normalised effective difficulty — the same hardware securing Bitcoin Cash or Litecoin also contributes to Quai's energy anchor at no extra energy cost.

Qi daily log-returns are regressed against modeled energy-cost returns and against BTC and ETH returns (the null hypotheses). The verdict requires energy to beat every null with a beta in [0.5, 1.5] and t-statistic > 2.

**Important:** the returns-based verdict is invariant to the choice of $/kWh or reference rig — those constants cancel in log-returns. They only affect level claims (joules/Qi, price-to-cost ratio), which are reported separately as a range.

### Claim 3 — Hardware benchmarking (`benchmark.py`)

```bash
# Measure inference joules/token on a GPU with Ollama running
python3 benchmark.py --minutes 5 --store --contributor your-handle

# Calibrate your mining rig for the claim-1 cost model
python3 benchmark.py --calibrate-rig                    # KawPoW GPU
python3 benchmark.py --calibrate-rig --algo sha256      # SHA-256 ASIC
python3 benchmark.py --calibrate-rig --algo scrypt      # Scrypt ASIC
```

Measurement boundary (stated explicitly in every stored row): marginal GPU board draw via NVML, no idle subtraction, excludes CPU/RAM/fans/PSU, PUE = 1.0, batch size 1. These choices can swing joules/token 2–5x; rows with different boundaries are never pooled.

ASIC calibration (`--algo sha256` / `--algo scrypt`) measures the rig's hashrate and watts, computes the energy factor relative to the KawPoW reference rig, and prints the `soap.reference_*` block to paste into `research.yaml`.

### Claim 5 — K-Quai controller

Miners choose QUAI or Qi as their block reward at mining time (`woHeader.lock`). The work is identical either way. The K-Quai controller watches a rolling 4,000-block window and adjusts the on-chain exchange rate to restore equilibrium. Three sub-tests:

- **P5a:** When miners prefer QUAI, the Qi-per-QUAI rate should rise (negative correlation).
- **P5b:** Miner preference should lead rate adjustments by ≥1 day.
- **P5c:** The market-implied rate (QUAI_USD / QI_USD) should track the on-chain rate within ±20%.

The thesis does not require miners to prefer Qi. Because QUAI and Qi are convertible at the protocol rate, the total energy expenditure is always reflected in the combined monetary base regardless of miner choice. Claim 5 tests whether the controller mechanism that enforces this is working.

---

## Configuration (`research.yaml`)

All thresholds, reference rig specs, API endpoints, and SOAP energy factors live in `research.yaml`. Key sections:

| Section | What it controls |
|---|---|
| `reference_gpu` | KawPoW reference rig (hashrate, watts) for claim-1 cost model |
| `soap.algo_energy_factors` | J/hash normalisation for SHA-256 and Scrypt workshares |
| `soap.reference_sha256/scrypt` | ASIC rig specs (populated by `benchmark.py --calibrate-rig --algo`) |
| `verdict` | Pre-registration switch (`thresholds_frozen`), liquidity gate, minimum samples |
| `claim5` | Controller directionality thresholds for P5a/P5b/P5c |

**Pre-registration:** while `verdict.thresholds_frozen` is `false`, every claim-1 output is stamped "THRESHOLDS DRAFT — not citable". Freeze the thresholds in `PREDICTIONS.md` (reviewed before seeing real output), flip the flag, and commit. Moving a number after seeing results voids the pre-registration.

---

## Project layout

```
reproduce.py              # one-command pipeline runner -> results/REPORT.md
fetch_data.py             # data fetching and caching
claim1_peg.py             # peg tracking (multi-algorithm energy model)
claim2_stability.py       # unit-of-account stability
benchmark.py              # joules/token measurement + ASIC/GPU rig calibration
qi_index.py               # live Qi cost of 1M tokens (joules/Qi × joules/token)
claim4_settlement.py      # micro-Qi escrow/settle/refund
claim5_token_choice.py    # K-Quai controller directionality
series.py                 # shared OLS regression and alignment utilities
sample_data.py            # deterministic synthetic fixtures for offline testing
test_claims.py            # 33 deterministic tests
research.yaml             # all configuration and pre-registered thresholds
PREDICTIONS.md            # falsifiable numeric predictions with failure conditions
OBJECTIONS.md             # steelmanned case against the thesis (10 objections)
CHANGELOG.md              # full change history
data/                     # cached data (JSON + CSV mirrors)
results/                  # claim outputs, charts, REPORT.md
tools/crossover-daemon/   # GPU auto-switcher (mining vs inference, USD-denominated)
legacy/                   # shelved marketplace prototype (frozen, not evidence)
```

---

## Contributing measurements (Claim 3)

Run `benchmark.py --minutes 5 --store --contributor your-handle` on your GPU and open a PR with the resulting `measurements.db` row. Hardware diversity is the point — the joules/token decline across hardware generations is itself a prediction (P3 in `PREDICTIONS.md`).

---

## Key distinctions

**Qi/joule is the stability claim. Qi/token is not.** Qi prices the energy input of computation. Joules per token falls every year as hardware and software improve, so Qi/token must fall too. That decline is predicted by this project (P3), not a failure mode.

**Protocol coupling is not market coupling.** Quai's protocol ties Qi emission to difficulty by construction — that is mechanics. The claim under test is whether Qi's *market price* tracks energy cost. Claim 1 tests the market layer only.

**SOAP workshares extend the energy anchor.** SHA-256 and Scrypt ASICs submitting workshares to Quai blocks contribute real energy to the network's security without any additional expenditure — the same work that secures BCH or LTC simultaneously anchors Qi's energy peg.

---

## License

MIT (see `LICENSE`).
