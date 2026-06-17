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
| 6 | **Dual-revenue model** | `claim6_workshare_inference.py` | Is the workshare subsidy to inference workers economically non-trivial? GPU IS the miner under TWP — models dual-revenue at Bitcoin-scale SOAP adoption. |
| 7 | **SOAP + TWP adoption** | `claim7_soap_adoption.py` | Is the SOAP/TWP workshare fraction of Quai's effective difficulty growing? Leading indicator of energy anchor broadening. |

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
# Measure inference joules/token on a GPU (Ollama backend, quick start)
python3 benchmark.py --minutes 5 --store --contributor your-handle

# Measure with InferenceGemm backend (emits Tensor Work Receipts)
# Set benchmark.backend: igemm in research.yaml first, then:
python3 benchmark.py --minutes 5 --store --contributor your-handle

# Calibrate your mining rig for the claim-1 cost model
python3 benchmark.py --calibrate-rig                    # KawPoW GPU
python3 benchmark.py --calibrate-rig --algo sha256      # SHA-256 ASIC
python3 benchmark.py --calibrate-rig --algo scrypt      # Scrypt ASIC
```

Two inference backends are supported. **Ollama** (`backend: ollama`) is the default and requires only `ollama pull qwen2.5:3b`. **InferenceGemm** (`backend: igemm`) drives the Dominant Strategies harness via a vLLM-compatible endpoint and emits a Tensor Work Receipt per inference run — the production backend for Quai-verifiable inference. The reference checkpoint is [`dominant-strategies/quai-igemm-qwen2.5-3b-w8a8-research`](https://huggingface.co/dominant-strategies/quai-igemm-qwen2.5-3b-w8a8-research) (Qwen2.5-3B, W8A8 quantization), with a measured TWP overhead of **2.98%** (64.49 → 62.57 tok/s). The pre-registered ceiling is 10% (P3b in `PREDICTIONS.md`).

Measurement boundary (stated explicitly in every stored row): marginal GPU board draw via NVML, no idle subtraction, excludes CPU/RAM/fans/PSU, PUE = 1.0, batch size 1. These choices can swing joules/token 2–5x; rows with different boundaries are never pooled.

ASIC calibration (`--algo sha256` / `--algo scrypt`) measures the rig's hashrate and watts, computes the energy factor relative to the KawPoW reference rig, and prints the `soap.reference_*` block to paste into `research.yaml`.

### Claim 5 — K-Quai controller

Miners choose QUAI or Qi as their block reward at mining time (`woHeader.lock`). The work is identical either way. The K-Quai controller watches a rolling 4,000-block window and adjusts the on-chain exchange rate to restore equilibrium. Three sub-tests:

- **P5a:** When miners prefer QUAI, the Qi-per-QUAI rate should rise (negative correlation).
- **P5b:** Miner preference should lead rate adjustments by ≥1 day.
- **P5c:** The market-implied rate (QUAI_USD / QI_USD) should track the on-chain rate within ±20%.

The thesis does not require miners to prefer Qi. Because QUAI and Qi are convertible at the protocol rate, the total energy expenditure is always reflected in the combined monetary base regardless of miner choice. Claim 5 tests whether the controller mechanism that enforces this is working.

### Claim 6 — Dual-revenue model and the Bitcoin merge-mining flywheel

The Quai team has confirmed (AMA, Jun 2026) that **Tensor Work Proof (TWP) inference will be added as a first-class merge-mining algorithm** alongside SHA-256 (BCH/BTC), Scrypt (LTC/DOGE), and Ravencoin KawPoW. This is the complete proof-of-useful-work loop: the GPU running InferenceGemm submits TWP receipts as native Quai workshares and earns Qi rewards. **The GPU IS the miner.** No co-located ASIC required. No time-sharing. The TWP receipt is the proof-of-work, the Qi reward is the block subsidy, and the inference fee is the transaction fee.

Project SOAP (Dec 2025) already enables the ASIC + GPU split configuration: a SHA-256 ASIC mines BTC/BCH and submits Quai workshares while a co-located GPU serves inference uninterrupted. TWP makes this even simpler — the GPU itself is the workshare submitter.

`claim6_workshare_inference.py` models the dual-revenue economics and includes a **Bitcoin-scale SOAP adoption table** showing outcomes at 0.01%–10% of Bitcoin's ~800 EH/s SHA-256 hashrate:

| BTC hashrate fraction | Adopted hashrate | Inference energy covered by workshares |
|---|---|---|
| 0.01% | 0.08 EH/s | Already significant relative to a single GPU node |
| 0.1% | 0.8 EH/s | GPU inference effectively free from an energy standpoint |
| 1% | 8 EH/s | Workshare revenue dwarfs GPU energy cost by orders of magnitude |

Until TWP launches on mainnet, the model uses KawPoW hashrate as a proxy for TWP receipts/sec. Once live, calibrate with `benchmark.py --calibrate-rig --algo twp`. This is a model of consequences, not a prediction. Claim 7 tracks whether those scenarios are becoming reality.

### Claim 7 — SOAP + TWP adoption as a leading indicator

`claim7_soap_adoption.py` tracks the SOAP and TWP workshare fraction of Quai's total effective difficulty over time and tests whether it is growing at a meaningful rate (pre-registered threshold: ≥1 percentage point per quarter). A positive result is direct on-chain evidence that:

1. The energy anchor is broadening — more diverse hardware (ASICs, inference GPUs) is contributing to Qi's energy backing.
2. The merge-mining flywheel is turning — miners and inference operators are finding SOAP/TWP participation profitable.
3. The inference node IS a Quai miner — TWP adoption means every GPU running InferenceGemm is a native workshare submitter.

TWP workshare fraction is tracked separately in `fetch_data.py` (`workshare_difficulty_twp_ws`) and will be reported alongside SOAP once the protocol launches on mainnet.

**Merge-mining precedent:** Namecoin has been merge-mined with Bitcoin since 2011, with ~50–60% of Bitcoin's hashrate participating despite NMC having negligible USD value. The barrier to SOAP/TWP adoption is software support, not miner incentive — the same barrier that was cleared for Namecoin with far less economic justification.

---

## Configuration (`research.yaml`)

All thresholds, reference rig specs, API endpoints, and SOAP energy factors live in `research.yaml`. Key sections:

| Section | What it controls |
|---|---|
| `reference_gpu` | KawPoW reference rig (hashrate, watts) for claim-1 cost model |
| `soap.algo_energy_factors` | J/hash normalisation for SHA-256, Scrypt, RVN, and TWP workshares |
| `soap.reference_sha256/scrypt/rvn/twp` | ASIC/GPU rig specs (populated by `benchmark.py --calibrate-rig --algo`) |
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
OBJECTIONS.md             # steelmanned case against the thesis (14 objections)
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

**The energy correlation precedes the reward mechanism — and does not depend on it.** This is the most important distinction in the project. Qi prices energy by construction. Inference costs energy by physics. Therefore Qi is the natural unit of account for inference right now, before TWP exists, before any workshare reward is paid. A customer paying for inference in Qi is paying in energy because that is what Qi is. This correlation is what Claims 1–3 test in live market data. TWP workshare rewards are the protocol's formalization of that relationship on-chain — a powerful reinforcement, but not the source of the anchor. Claim 6 models the reward mechanism. Claims 1–3 establish the energy correlation that makes the reward meaningful in the first place.

**TWP is a reward mechanism, not the source of the energy anchor.** When TWP launches, a GPU submitting Tensor Work Proof receipts as workshares will earn Qi block rewards directly. This makes the economics of running an inference node more attractive and closes the proof-of-useful-work loop at the protocol level. But the energy-inference-Qi relationship exists independently of this mechanism. Removing TWP from the picture does not break the thesis — it only removes one of the incentive layers that reinforces it.

**SOAP and TWP extend the energy anchor.** SHA-256 ASICs (BCH/BTC), Scrypt ASICs (LTC/DOGE), and Ravencoin KawPoW GPUs submitting SOAP workshares contribute real energy to the network without any additional expenditure. TWP goes further: the Quai team has confirmed that GPU inference nodes running InferenceGemm will submit Tensor Work Proof receipts as native workshares, earning Qi rewards. The GPU IS the miner. Claims 6 and 7 model and track this mechanism.

**The Bitcoin merge-mining flywheel.** If SOAP and TWP adoption grows, more of Bitcoin's ~800 EH/s SHA-256 hashrate and more GPU inference capacity flows into Quai's energy anchor. Under TWP, the GPU itself earns the workshare reward — no ASIC needed. Claim 7 is the early warning system for whether this flywheel is turning.

---

## License

MIT (see `LICENSE`).
