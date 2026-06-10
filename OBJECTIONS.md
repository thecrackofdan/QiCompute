# Objections — steelmanned

The strongest cases against the thesis, stated as their proponents would
state them. The repo's design answers some; others are open risks that the
data may confirm. Failure on any of these is publishable, not buryable.

## (a) The Qi/token vs Qi/joule confusion

**Objection:** "Energy money for compute" invites the reading that AI work
gets a stable price in Qi. It does not. Joules/token falls every year —
roughly an order of magnitude per ~4 years through hardware (3090→4090→5090)
and software (quantization, speculative decoding, better kernels). Anyone
holding Qi expecting "1M tokens costs the same next year" is structurally
guaranteed to be wrong, and a marketing narrative that blurs input and output
pricing is selling that error.

**Treatment here:** the corollary is stated in the README before the claims,
claim 2 prints it next to every table, and PREDICTIONS.md P3 makes the
*decline* of joules/token the prediction. If an output of this repo ever
presents Qi/token as the stability result, that output is wrong by the
repo's own standard.

## (b) Electricity costs vary 5–10x by region

**Objection:** "The energy cost of production" is not one number. Industrial
power runs ~$0.03/kWh in hydro-rich regions and $0.30+/kWh in parts of
Europe; a peg to "energy cost" is a peg to nothing in particular.

**Treatment here — the global marginal miner assumption, made explicit:**
the cost model prices the *marginal* producer, not the average one. Mining
migrates to cheap power; difficulty equilibrates so that the marginal miner
operates near break-even at *their* electricity price. The model's
`usd_per_kwh` in `research.yaml` is therefore a single global-marginal
estimate (default $0.12, deliberately conservative), and the honest
sensitivity check is to rerun claim 1 at $0.04 and $0.20 — if the verdict
flips inside the plausible range of the marginal miner's power cost, the
result is not robust and the report must say so. Regional spread is also why
claim 2 uses a configurable electricity index rather than pretending one
price exists.

## (c) Why not just USD, or electricity futures?

**Objection:** if you want energy-stable pricing, denominate compute in USD
indexed to an electricity benchmark, or hedge with power futures. Deep, ,
liquid, regulated markets already exist; a thinly-traded token adds
counterparty and volatility risk for no benefit.

**Steelman response being tested, not assumed:** an index quotes but cannot
settle (claim 4's whole point); electricity futures settle financially in
USD at regional hubs, are inaccessible to a GPU owner in most jurisdictions,
and hedge a *location*, not a unit of account. Qi is the only candidate in
which mining gives the unit an automatic production-cost arbitrage *and* the
unit itself is transferable money. **But** this argument only survives if
claim 1 holds — if Qi doesn't track energy cost, "USD plus an index" wins
outright and the repo will have demonstrated exactly that.

## (d) Qi liquidity may be too thin for its price to mean anything

**Objection:** a price series from a few thousand dollars of daily volume on
minor exchanges is noise. Correlations computed on it — for or against the
thesis — are not measurements of an "energy money" mechanism; they are
artifacts of market-making bots and a handful of trades.

**Treatment here:** `fetch_data.py` caches the daily volume series alongside
price, and claim 1's output includes median/min/max daily volume in the same
report as the verdict — the conclusion and its liquidity caveat travel
together. There is no volume threshold below which results are hidden;
thin volume is itself a finding: "the energy-money thesis is currently
untestable at this liquidity" is a legitimate outcome of this research, and
it would be reported as the headline rather than worked around.

## (e) Cost of production does not cause price (the Bitcoin lesson)

**Objection:** a decade of Bitcoin data shows causality runs price →
hashrate → difficulty → cost, not the reverse. Cost of production *follows*
price with a lag because difficulty adjusts until marginal miners break
even. So claim 1's correlation, even if found, may show difficulty chasing
price — not an energy anchor stabilizing it.

**Treatment here:** acknowledged as the sharpest objection. Correlation in
claim 1 cannot establish causal direction. The repo reports the
relationship and its strength; lead/lag analysis (does cost predict price,
or price predict cost?) is the natural follow-up if claim 1's correlation
exists at all, and the conclusion language in PAPER.md is required to say
"tracks", never "is caused by", until that work is done.
