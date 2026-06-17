# Predictions

Written **before** results. Each prediction is numeric, falsifiable, labeled
**[Qi/joule]** or **[Qi/token]**, and states both its failure condition and
the **data conditions** (liquidity, time window) required to evaluate it at
all. Candidate thresholds below are **priors awaiting derivation from the
first real data pull** — run `python3 reproduce.py`, read
`results/claim1_stats.json` and `results/claim2_stats.json`, replace the
bracketed candidates, and have the final numbers reviewed BEFORE any results
are interpreted. Once frozen, these numbers do not move to fit the data.

Status: **DRAFT — thresholds flagged for review (data not yet pulled).**

**Freeze mechanics (enforced in code):** while `verdict.thresholds_frozen`
is `false` in `research.yaml`, every claim-1 output is stamped
"THRESHOLDS DRAFT — not citable". To freeze: replace every bracketed
candidate below with a reviewed number — ideally reviewed by someone who
*doubts* the thesis — set the flag to `true`, and commit. The freeze must
happen **before** looking at real regression output; flipping the flag (or
moving a number) after seeing results voids the pre-registration and the
repo's neutrality claim with it.

## Why only Qi/joule predictions are central

Qi prices the energy **input** of computation. Qi/joule is what the
energy-money thesis predicts is stable. Qi/token is a *derived* quantity —
Qi/joule × joules/token — and joules/token falls every year with hardware
and software efficiency, so Qi/token is predicted to **decline**, not hold.
A stable Qi/token over a multi-year horizon would actually *contradict* the
corollary. Predictions below are labeled accordingly; only the [Qi/joule]
ones test the thesis itself.

## Evaluability preconditions (apply to P1 and P2)

Market-price predictions are only evaluable when the market price means
something:

- **Liquidity:** median daily Qi volume ≥ `[$50,000]`
  (`verdict.min_median_daily_volume_usd` in `research.yaml`; candidate
  rationale: a single plausible $5k hedging trade should move < 10% of a
  day's volume). Below this, claim 1 outputs `below_liquidity_threshold`
  and **no conclusion is drawn in either direction** — "currently
  untestable at this liquidity" is the reported finding.
- **Window:** ≥ 90 aligned daily observations (`verdict.min_samples`);
  evaluation uses the full available history at freeze time, never a
  sub-window selected after seeing data.
- If Qi volume data is unavailable from the source, that is reported
  alongside the verdict and weakens it; it is never silently ignored.

## P1 — Peg tracking **[Qi/joule]** (claim 1)

Tests **market-level** coupling only. Protocol-level coupling (emission tied
to difficulty) is true by construction and is not a prediction — see
OBJECTIONS.md (f).

**Prediction:** Over the full available daily history, Qi log-returns are
better explained by modeled energy-cost returns than by **every**
crypto-beta null (BTC and ETH):

- R²(Qi ~ energy cost) > max(R²(Qi ~ BTC), R²(Qi ~ ETH)), and
- energy-cost beta in **[0.5, 1.5]** with t-statistic > 2.

**Candidate magnitudes (priors, to derive):** R²(energy) ≥ [0.2]; the gap
R²(energy) − max(null R²) ≥ [0.1].

**Failure condition:** any null R² ≥ R²(Qi ~ energy cost), or energy beta
≤ 0, or |t| ≤ 2 on the full sample. Any of these means Qi trades as crypto
beta over the observed window and claim 1 fails.

**Scale-invariance note:** this returns-based prediction is invariant to
the cost model's constants ($/kWh, reference hashrate/watts) — they cancel
in log-returns, so no choice of global-marginal electricity price can flip
it; in returns space the test is effectively Qi versus difficulty. Those
constants matter only for *level* claims (joules/Qi, the price-to-cost
ratio, the index), which claim 1 reports with a $0.04–$0.20/kWh range and
which carry no pass/fail condition here.

**Multi-algorithm note (SOAP):** Since Project SOAP (Dec 2025), SHA-256
(BCH/BTC) and Scrypt (LTC/DOGE) ASICs submit workshares to Quai blocks.
The cost model in claim 1 is extended to account for this additional energy
via an energy-normalised effective difficulty (see `claim1_peg.py`). The
returns-based verdict is invariant to this extension (workshare difficulty
also cancels in log-returns); the extension only affects level claims. When
workshare difficulty data is available, the output notes which algorithms
contributed. When unavailable, the single-algorithm KawPoW baseline is used
and the output notes that the energy anchor is an undercount.

**Data conditions:** the evaluability preconditions above. Below either
threshold the output is `insufficient_data` / `below_liquidity_threshold`,
reported as such.

## P2 — Unit-of-account stability **[Qi/joule]** (claim 2)

**Prediction:** Over a 12-month window, the Qi price of 1 kWh of compute
energy (Qi/joule, via market rates) stays within **±[X = 25]%** of its
window mean, while the same energy priced in USD GPU-hour rental rates
varies **±[Y = 50]%** and priced in BTC varies more than in Qi:

- mean 30-day rolling volatility: vol(1 kWh in Qi) < vol(1 kWh in BTC), and
- vol(1 kWh in Qi) < vol(USD/GPU-hour rental of equivalent hardware).

X and Y above are priors; derive candidates from the first pull and flag
for review.

**Failure condition:** Qi-denominated compute energy is no less volatile
than BTC-denominated over the same full window, or exceeds the frozen ±X%
band while USD/GPU-hour stays inside ±Y%.

**Data conditions:** same evaluability preconditions as P1 (the Qi leg of
every bundle price runs through the market Qi/USD rate), plus ≥ 12 months of
overlapping history for the named comparators.

**Corollary guard (always in force):** the stable series claimed is
**Qi/joule**. If a chart shows Qi/token stable over a multi-year horizon,
that contradicts the corollary and must be flagged, not celebrated.

## P3 — Joules/token ground truth **[Qi/token side: the declining input]** (claim 3)

This prediction is about the *physical* input that makes Qi/token a
declining quantity; it involves no market data.

**Prediction:** Measured joules/token for Llama-70B-class inference declines
at least **[15]% per year** across the contributed-hardware dataset (median
across submissions, same model class, same measurement boundary), as
hardware and software efficiency improve. On *fixed* hardware + software,
repeated measurement is stable within **±[10]%**.

**Failure condition (for the corollary, not the thesis):** the
cross-hardware median joules/token does not decline year-over-year. This
would remove the main reason Qi/token cannot be the stable series — and
would itself be a publishable finding.

**Data conditions:** ≥ [5] independent hardware submissions per comparison
year, all reporting the same measurement boundary (marginal GPU board draw,
PUE 1.0, batch 1 — see claim 3 methodology in the README); boundaries that
differ are not pooled.

## P4 — Settlement **[Qi/token as a derived price, not a stability claim]** (claim 4)

Settlement quotes jobs in Qi/token *derived from* Qi/joule × joules/token at
settlement time; nothing here predicts that quote is stable over time.

**Prediction:** The escrow→settle→refund cycle conserves micro-Qi exactly
(integer arithmetic, zero drift) over **[10,000]** randomized job cycles,
and re-running any settlement is a no-op (no double-pay) in 100% of cases.

**Failure condition:** any cycle that creates, destroys, or double-pays a
single micro-Qi. This is an engineering claim with no statistical wiggle
room.

**Data conditions:** none (deterministic; a seeded 300-cycle version runs in
CI as `test_claims.py::SettlementConservationFuzzTest`).

## P5 — Miner token choice, directionality & thesis robustness **[on-chain controller]** (claim 5)

Miners elect their block reward denomination (QUAI or Qi) via the `woHeader.lock` field at
block time. The work is identical regardless of choice. The K-Quai controller observes a
rolling 4,000-block preference window and adjusts the on-chain QUAI↔Qi exchange rate via
a logistic regression (alpha = 1/1000) to restore equilibrium.

**P5a — Controller directionality:**
When miners prefer QUAI (low `qi_fraction`), the on-chain Qi-per-QUAI exchange rate should
rise. We expect `corr(qi_fraction[t-1], Δexchange_rate[t]) < 0`.

**P5b — Miner preference leads rate adjustments:**
A shift in miner preference should precede the exchange rate adjustment by at least 1 day.
We expect a negative lagged cross-correlation peak at lag k ≥ 1 day:
`corr(Δexchange_rate[t], qi_fraction[t-k]) < -0.05` for some k in {1..14}.

**P5c — Market rate tracks on-chain protocol rate:**
The market-implied exchange rate (QUAI_USD / QI_USD) should track the on-chain K-Quai
controller rate within **±[20]%** over any 30-day window. Wide persistent divergence
would indicate the controller is failing to anchor the peg.

**Failure conditions:**
- P5a fails if `corr(qi_fraction[t-1], Δexchange_rate[t]) ≥ 0` with n ≥ 90 observations.
- P5b fails if no lag in {1..14} days shows correlation < -0.05.
- P5c fails if the market/on-chain ratio exceeds ±20% for more than 30 consecutive days.
  When QI market price is unavailable, P5c is reported as `insufficient_data` (not a failure).

**Data conditions:**
- P5a and P5b require ≥ [90] days of aligned `token_choice_qi_fraction` and
  `exchange_rate_qi_per_quai` from the on-chain RPC scan.
- P5c additionally requires a QI/USD market price series (CoinGecko or equivalent).
  If unavailable, P5c is `insufficient_data` and does not affect the P5a/P5b verdict.

**Thesis robustness note:**
The energy-money thesis does not require miners to prefer Qi. Because QUAI and Qi are
convertible at the protocol rate, the total energy expenditure (captured by difficulty)
is always reflected in the combined monetary base regardless of miner token choice.
The miner preference ratio is a leading indicator of peg pressure, not a failure mode.

## P6 — Workshare-for-inference dual-revenue model **[Qi/joule]** (claim 6)

**Prediction:** At current network difficulty and a reference RTX 3090 (45 MH/s, 300 W),
workshare rewards cover **≥ [5]%** of the energy cost of running inference continuously.
This threshold is intentionally conservative — the claim is that the dual-revenue model
is economically non-trivial, not that it is sufficient alone.

**What is being tested:** whether a GPU that simultaneously mines Quai (submitting
KawPoW workshares) and serves inference (earning customer payment) receives a meaningful
subsidy from workshare rewards. The workshares are standard partial proofs — not AI
outputs used as consensus. The dual-revenue model is the operational complement to
claim 1: if Qi prices energy, then workshare rewards denominated in Qi are a direct
energy subsidy to inference workers.

**Failure conditions:**
- P6 fails if `workshare_coverage_fraction < 0.05` at current network difficulty
  with the reference rig parameters in `research.yaml`.
- P6 is `insufficient_data` if no real difficulty data is available (sample mode only).

**Data conditions:**
- Requires real network difficulty from `fetch_data.py`.
- Requires `joules_per_token` from `benchmark.py --store` or the config fallback
  (labeled as fallback in output).
- The `workshare_difficulty_factor` in `research.yaml → claim6` must be calibrated
  against observed workshare inclusion rates before the result is citable.

**Sensitivity:** the sensitivity table in `results/claim6.md` shows coverage across
a 4x hashrate range and 50x difficulty range. The pre-registered threshold must hold
at the reference rig parameters; sensitivity is reported as context, not as a
pass/fail gate.

## Evaluation discipline

- The evaluation window is the **full available history** at freeze time —
  no sub-window selection after seeing data.
- Thin data (low volume, short history) is reported with the result, per
  OBJECTIONS.md (d); below the pre-registered thresholds the result *is*
  the untestability.
- A failed prediction is published with the same prominence as a confirmed
  one.
