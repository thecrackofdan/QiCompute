# Predictions

Written **before** results. Each prediction is numeric, falsifiable, and has
an explicit failure condition. Candidate thresholds below are **priors
awaiting derivation from the first real data pull** — run
`python3 reproduce.py`, read `results/claim1_stats.json` and
`results/claim2_stats.json`, replace the bracketed candidates, and have the
final numbers reviewed BEFORE any results are interpreted. Once frozen, these
numbers do not move to fit the data.

Status: **DRAFT — thresholds flagged for review (data not yet pulled).**

## P1 — Peg tracking (claim 1)

**Prediction:** Over the full available daily history, Qi log-returns are
better explained by modeled energy-cost returns than by BTC returns:

- R²(Qi ~ energy cost) > R²(Qi ~ BTC), and
- energy-cost beta in **[0.5, 1.5]** with t-statistic > 2.

**Candidate magnitudes (priors, to derive):** R²(energy) ≥ [0.2]; the gap
R²(energy) − R²(BTC) ≥ [0.1].

**Failure condition:** R²(Qi ~ BTC) ≥ R²(Qi ~ energy cost), or energy beta
≤ 0, or |t| ≤ 2 on the full sample. Any of these means Qi trades as crypto
beta over the observed window and claim 1 fails. Fewer than 90 aligned daily
observations means no verdict either way (`insufficient_data`), reported as
such.

## P2 — Unit-of-account stability (claim 2)

**Prediction:** Over a 12-month window, the Qi price of 1 kWh of compute
energy (Qi/joule, via market rates) stays within **±[X = 25]%** of its
window mean, while the same energy priced in USD GPU-hour rental rates
varies **±[Y = 50]%** and priced in BTC varies more than in Qi:

- mean 30-day rolling volatility: vol(1 kWh in Qi) < vol(1 kWh in BTC), and
- vol(1 kWh in Qi) < vol(USD/GPU-hour rental of equivalent hardware).

X and Y above are priors; derive candidates from the first pull (Qi-vs-BTC
volatility history; Vast.ai/RunPod 3090 rate history if obtainable) and flag
for review.

**Failure condition:** Qi-denominated compute energy is no less volatile
than BTC-denominated over the same full window, or exceeds the frozen ±X%
band while USD/GPU-hour stays inside ±Y%.

**Corollary guard (always in force):** the stable series claimed is
**Qi/joule**. Qi/token is *predicted to decline* as joules/token falls; if a
chart shows Qi/token stable over a multi-year horizon, that contradicts the
corollary and must be flagged, not celebrated.

## P3 — Joules/token ground truth (claim 3)

**Prediction:** Measured joules/token for Llama-70B-class inference declines
at least **[15]% per year** across the contributed-hardware dataset (median
across submissions, same model class), as hardware and software efficiency
improve. On *fixed* hardware + software, repeated measurement is stable
within **±[10]%**.

**Failure condition (for the corollary, not the thesis):** the cross-
hardware median joules/token does not decline year-over-year. This would
remove the main reason Qi/token cannot be the stable series — and would
itself be a publishable finding.

## P4 — Settlement (claim 4)

**Prediction:** The escrow→settle→refund cycle conserves micro-Qi exactly
(integer arithmetic, zero drift) over **[10,000]** randomized job cycles,
and re-running any settlement is a no-op (no double-pay) in 100% of cases.

**Failure condition:** any cycle that creates, destroys, or double-pays a
single micro-Qi. This is an engineering claim with no statistical wiggle
room.

## Evaluation discipline

- The evaluation window is the **full available history** at freeze time —
  no sub-window selection after seeing data.
- Thin data (low volume, short history) is reported with the result, per
  OBJECTIONS.md (d).
- A failed prediction is published with the same prominence as a confirmed
  one.
