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

**Treatment here — the global marginal miner assumption, made explicit, and
what it can actually contaminate:** the cost model prices the *marginal*
producer, not the average one. Mining migrates to cheap power; difficulty
equilibrates so that the marginal miner operates near break-even at *their*
electricity price. The model's `usd_per_kwh` in `research.yaml` is a single
global-marginal estimate (default $0.12, deliberately conservative).

Crucially, the claim-1 **verdict is immune to this assumption by
construction**: the $/kWh (and reference hashrate/watts) are constant
multipliers on the cost series, and constant multipliers cancel in
log-returns — in returns space the regression is effectively Qi versus
difficulty, and no choice of electricity price can flip it. What the
assumption *does* contaminate is every **level** claim — how far above or
below modeled production cost Qi trades, joules/Qi, the Qi index, claim 2's
bundles. Claim 1 therefore reports the median price-to-cost ratio at $0.04,
$0.12, and $0.20 per kWh side by side, and any level statement must quote
that range, not a single number. Regional spread is also why claim 2 uses a
configurable electricity index rather than pretending one price exists.

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

**Treatment here — a pre-registered threshold, not a judgment call:**
`fetch_data.py` caches the daily volume series alongside price, and claim 1
applies `verdict.min_median_daily_volume_usd` (candidate **$50,000** median
daily volume, rationale in PREDICTIONS.md: a plausible single $5k hedging
trade should move less than 10% of a day's volume). Below the threshold,
claim 1's verdict is `below_liquidity_threshold` — the regression stats are
still printed for inspection, but **no conclusion is drawn in either
direction**. Median/min/max daily volume appears in the same report as the
verdict, so the conclusion and its liquidity caveat travel together. Thin
volume is itself a finding: "the energy-money thesis is currently untestable
at this liquidity" is a legitimate headline outcome of this research, and if
current liquidity is below the threshold the repo says exactly that rather
than drawing conclusions.

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

## (f) Isn't "Qi tracks energy cost" true by construction?

**Objection:** Quai's protocol ties Qi emission to hashrate and difficulty.
Difficulty adjustment guarantees a mechanical relationship between energy
expended and Qi issued. So claim 1 is testing a tautology dressed up as an
empirical question.

**Treatment here — the protocol/market distinction, made explicit:** the
objection is correct about the protocol layer, and the repo agrees:
**protocol-level coupling (emission schedule, difficulty adjustment) is true
by design and is not a finding.** What is *not* guaranteed by any protocol
is that Qi's **exchange price** — what the market pays for a Qi in USD —
tracks the energy cost of producing one. Bitcoin has identical protocol
mechanics and its market price spends years multiples above or below
production cost. Claim 1's regressions run on **market price**, the null
hypothesis (BTC beta) exists precisely because market prices can decouple
from production mechanics, and the claim-1 docstring and output state which
layer is under test. If someone reads a claim-1 confirmation as "the
protocol works as designed," they have misread it; the protocol working as
designed is the *premise*, not the result.

## (g) Isn't energy a minority of real compute cost?

**Objection:** for the hardware that actually serves frontier AI, energy is
a rounding error. An H100 amortizes ~$20+/day in capex against ~$1.50/day in
electricity — energy is well under 10% of total cost. A unit of account
that tracks 7% of the cost structure is not "the natural money for compute."

**Treatment here — the energy-marginal scope, stated and bounded:** the
thesis never claims Qi prices *all* compute cost; it prices the **energy
component**, and the claim is strongest where electricity dominates
*marginal* cost: depreciated/sunk-capex consumer GPUs on power the operator
already buys — a miner's idle 3090 is ~100% energy at the margin. The README
Scope and Limitations table makes the fraction explicit across hardware
classes (sunk 3090 ≈ 100% of marginal cost; amortized 3090 ≈ 40–45%;
datacenter H100 ≈ 7%). That scope is honest about what it excludes: the
H100 fleet is *outside* the thesis's strong zone, and any conclusion drawn
here applies to energy-marginal compute, not to datacenter economics. If
the addressable pool of energy-marginal compute turns out to be too small
to matter, that is a market-size objection worth its own analysis — but it
is not an error in the unit-of-account argument.

## (h) Why isn't this just another decentralized AI marketplace?

**Objection:** strip the energy language and this is the same pitch as a
dozen GPU-marketplace tokens: rent out idle GPUs, settle in our coin. Those
projects assume their token is a sensible pricing unit; so does this.

**Treatment here:** that assumption is exactly what this repository
refuses to make — **the repository first tests whether Qi is a valid unit
of account for computation before building a marketplace around it.** The
previous incarnation of this repo *was* the marketplace; it was shelved into
`legacy/` precisely because it assumed its own premise, and the README says
so. The project ordering is enforced structurally: claim 1 (does the peg
exist?) gates claim 2 (is it a better unit of account?), which gates the
index, which gates settlement — and the marketplace layer does not exist at
all. If claim 1 fails, the honest output of this project is "do not build
a Qi-priced compute marketplace," published as prominently as the opposite.
Two further differences from the generic pitch: the chain stays
proof-of-work (no proof-of-useful-work, no AI consensus — Quai secures the
money layer, compute lives above it), and settlement here prices only the
energy component of jobs, per (g).
