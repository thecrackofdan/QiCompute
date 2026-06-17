# QiCompute

An empirical research toolkit that tests whether **Qi** — the energy-denominated token of Quai Network — can function as a natural unit of account for AI inference compute. It measures the physics, runs the regressions, and delivers a reproducible verdict.

---

## What it does

QiCompute pulls live on-chain and market data, runs seven falsifiable claims against it, and writes a full report to `results/REPORT.md`. Every number is traceable back to a cached data file; every verdict has a pre-registered failure condition.

The seven claims, in order of dependency:

| # | Claim | Script | What it tests |
|---|---|---|---|
| 1 | **Peg tracking** | `claim1_peg.py` | Does Qi's market price track its modeled energy cost of production, beating BTC and ETH as null hypotheses? |
| 2 | **Unit-of-account stability** | `claim2_stability.py` | Is compute energy more stably priced in Qi than in USD or BTC? (Rolling 30-day volatility comparison) |
| 3 | **Joules/token ground truth** | `benchmark.py` | Measured tokens/sec, watts, and joules/token on real hardware, stored in a public-dataset SQLite schema |
| 4 | **Settlement** | `claim4_settlement.py` | Escrow → settle → refund cycle in micro-Qi, conservation-checked and receipt-emitting |
| 5 | **K-Quai controller** | `claim5_token_choice.py` | Does the on-chain QUAI↔Qi exchange rate respond to miner token preference as the monetary theory predicts? |
| 6 | **Dual-revenue model** | `claim6_workshare_inference.py` | Is the workshare subsidy to inference workers economically non-trivial? Models GPU + ASIC split at Bitcoin-scale SOAP adoption. |
| 7 | **SOAP adoption** | `claim7_soap_adoption.py` | Is the SOAP workshare fraction of Quai's effective difficulty growing? Leading indicator of energy anchor broadening. |

---

## Quick start

```bash
pip install -r requirements.txt

# Full pipeline: fetch live data, run all seven claims, write results/REPORT.md
python3 reproduce.py

# Offline demo with synthetic data (labeled, not findings)
python3 reproduce.py --sample

# Live at-a-glance dashboard (auto-refresh every 60s)
python3 qi_dashboard.py --watch 60

# Run the test suite (41 deterministic tests)
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

### Claim 6 — Dual-revenue model and the Bitcoin merge-mining flywheel

Project SOAP allows SHA-256 ASICs (Bitcoin Cash / Bitcoin hardware) and Scrypt ASICs (Litecoin / Dogecoin hardware) to submit workshares to Quai blocks and earn QUAI rewards — for the same hash that already secures their primary chain. The BCH/LTC block reward flows to a protocol-controlled buyback address; the miner earns QUAI on top.

This creates the cleanest version of the dual-revenue model: a **SHA-256 ASIC mines BTC/BCH and submits Quai workshares; a co-located GPU serves inference uninterrupted**. No GPU time-sharing. No probabilistic interleaving. The ASIC handles workshare submission; the GPU is free to run inference at full capacity.

`claim6_workshare_inference.py` models the economics of this configuration and includes a **Bitcoin-scale SOAP adoption table** showing dual-revenue outcomes at 0.01%–10% of Bitcoin's ~800 EH/s SHA-256 hashrate:

| BTC hashrate fraction | Adopted hashrate | Inference energy covered by ASIC workshares |
|---|---|---|
| 0.01% | 0.08 EH/s | Already significant relative to a single GPU node |
| 0.1% | 0.8 EH/s | GPU inference effectively free from an energy standpoint |
| 1% | 8 EH/s | ASIC workshare revenue dwarfs GPU energy cost by orders of magnitude |

This is a model of consequences, not a prediction. Claim 7 tracks whether those scenarios are becoming reality.

### Claim 7 — SOAP adoption as a leading indicator

`claim7_soap_adoption.py` tracks the SOAP workshare fraction of Quai's total effective difficulty over time and tests whether it is growing at a meaningful rate (pre-registered threshold: ≥1 percentage point per quarter). A positive result is direct on-chain evidence that:

1. The energy anchor is broadening — more diverse hardware is contributing to Qi's energy backing.
2. The merge-mining flywheel is turning — ASIC miners are finding SOAP participation profitable.
3. The ASIC + GPU split configuration (Claim 6) is becoming a standard node setup.

**Merge-mining precedent:** Namecoin has been merge-mined with Bitcoin since 2011, with ~50–60% of Bitcoin's hashrate participating despite NMC having negligible USD value. The barrier to SOAP adoption is pool software support, not miner incentive — the same barrier that was cleared for Namecoin with far less economic justification.

---

## Configuration (`research.yaml`)

All thresholds, reference rig specs, API endpoints, and SOAP energy factors live in `research.yaml`. Key sections:

| Section | What it controls |
|---|---|
| `reference_gpu` | KawPoW reference rig (hashrate, watts) for claim-1 cost model |
| `soap.algo_energy_factors` | J/hash normalisation for SHA-256 and Scrypt workshares |
| `soap.reference_sha256/scrypt` | ASIC rig specs (populated by `benchmark.py --calibrate-rig --algo`) |
| `claim6` | Workshare difficulty factor, block reward, coverage threshold |
| `claim7` | SOAP adoption growth threshold, minimum fraction, BTC hashrate reference |
| `verdict` | Pre-registration switch (`thresholds_frozen`), liquidity gate, minimum samples |
| `claim5` | Controller directionality thresholds for P5a/P5b/P5c |

**Pre-registration:** while `verdict.thresholds_frozen` is `false`, every claim-1 output is stamped "THRESHOLDS DRAFT — not citable". Freeze the thresholds in `PREDICTIONS.md` (reviewed before seeing real output), flip the flag, and commit. Moving a number after seeing results voids the pre-registration.

---

## Project layout

```
reproduce.py              # one-command pipeline runner -> results/REPORT.md
qi_dashboard.py           # live CLI dashboard (--watch N for auto-refresh)
fetch_data.py             # data fetching and caching
claim1_peg.py             # peg tracking (multi-algorithm energy model)
claim2_stability.py       # unit-of-account stability
benchmark.py              # joules/token measurement + ASIC/GPU rig calibration
qi_index.py               # live Qi cost of 1M tokens (joules/Qi × joules/token)
claim4_settlement.py      # micro-Qi escrow/settle/refund
claim5_token_choice.py    # K-Quai controller directionality
claim6_workshare_inference.py  # dual-revenue model + BTC-scale SOAP scenarios
claim7_soap_adoption.py   # SOAP adoption rate as energy anchor leading indicator
series.py                 # shared OLS regression and alignment utilities
sample_data.py            # deterministic synthetic fixtures for offline testing
test_claims.py            # 41 deterministic tests
research.yaml             # all configuration and pre-registered thresholds
PREDICTIONS.md            # falsifiable numeric predictions with failure conditions
OBJECTIONS.md             # steelmanned case against the thesis (12 objections)
PAPER.md                  # academic paper skeleton wired to results/ artifacts
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

**SOAP workshares extend the energy anchor.** SHA-256 and Scrypt ASICs submitting workshares to Quai blocks contribute real energy to the network's security without any additional expenditure — the same work that secures BCH or LTC simultaneously anchors Qi's energy peg. Claims 6 and 7 model and track this mechanism.

**The Bitcoin merge-mining flywheel.** If SOAP adoption grows, more of Bitcoin's ~800 EH/s SHA-256 hashrate flows into Quai's energy anchor. At even 1% adoption, the ASIC workshare revenue for a co-located inference node dwarfs its GPU energy cost — making Qi-priced inference economically self-sustaining from the energy side. Claim 7 is the early warning system for whether this flywheel is turning.

---

## License

MIT (see `LICENSE`).
