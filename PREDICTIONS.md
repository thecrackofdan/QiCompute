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

## Evaluation discipline

- The evaluation window is the **full available history** at freeze time —
  no sub-window selection after seeing data.
- Thin data (low volume, short history) is reported with the result, per
  OBJECTIONS.md (d); below the pre-registered thresholds the result *is*
  the untestability.
- A failed prediction is published with the same prominence as a confirmed
  one.
