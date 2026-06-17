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

## (i) If miners choose QUAI over Qi, the energy peg breaks

**Objection:** miners choose their block reward denomination at block time. If they
systematically prefer QUAI, Qi supply contracts relative to the energy being expended,
the peg weakens, and the energy-money thesis fails in practice even if it holds in theory.

**Treatment here — the work is identical; directionality preserves the anchor:**
the objection conflates token preference with energy decoupling. The work a miner
performs — hashing — is identical regardless of which token they elect. The total
energy expenditure of the network is captured by **difficulty**, not by token choice.
Qi's linear emission is pegged to difficulty; even if every miner elected QUAI today,
the *potential* Qi supply (the amount that would be issued if miners switched) is still
anchored to the same difficulty.

The K-Quai controller closes the loop: it observes miner token preference over a
rolling 4,000-block window and adjusts the on-chain QUAI↔Qi exchange rate via a
logistic regression (alpha = 1/1000) with a cubic discount function (minimum 20 bps
slip, scaling cubically with volume). When miners prefer QUAI:

1. Qi supply contracts → Qi price rises above energy cost.
2. Rational actors convert QUAI to Qi at the protocol rate (burning QUAI, minting Qi).
3. Supply expands back toward equilibrium.

The controller's response is measurable: the `header.exchangeRate` field in every
block header records the current Qi-per-QUAI rate. **Claim 5 tests this empirically:**
if the controller is working, the exchange rate should rise when miners prefer QUAI
(P5a), and that rise should lag the preference shift by at least one day (P5b).

The miner token choice ratio is therefore a **leading indicator of peg pressure**,
not a failure mode. A sustained preference for QUAI is the system working as designed:
it signals that the market expects QUAI to appreciate faster than energy costs rise,
and the controller responds by making Qi more attractive until equilibrium is restored.

**What would actually break the thesis:** if the controller's logistic regression
consistently moved the exchange rate in the *wrong* direction (P5a fails), or if the
market-implied rate (QUAI_USD / QI_USD) diverged persistently from the on-chain rate
(P5c fails). Those are the testable failure modes, and claim 5 is designed to catch them.

## (j) SOAP workshares make the energy model incomplete — SHA-256 and Scrypt energy is unaccounted for

**Objection:** Since Project SOAP (Dec 2025), SHA-256 ASICs (Bitcoin Cash hardware) and
Scrypt ASICs (Litecoin/Dogecoin hardware) can submit workshares to Quai blocks and earn
QUAI rewards. These ASICs expend real energy, but the claim-1 cost model only uses KawPoW
difficulty — so the modeled cost of producing one Qi is an undercount of the true network
energy expenditure. A peg that understates the energy input is not a real energy peg.

**Treatment here:** The claim-1 cost model is extended to account for SOAP workshare
energy via an energy-normalised effective difficulty (see `claim1_peg.py`):

    total_effective_difficulty = kawpow_difficulty
                               + sum(ws_difficulty[algo] * energy_factor[algo])

where `energy_factor[algo]` converts each algorithm's difficulty into KawPoW-equivalent
energy units (J per hash differs by algorithm). Default factors are derived from published
ASIC specs and stored in `research.yaml` under `soap.algo_energy_factors`; they can be
replaced with measured values via `python3 benchmark.py --calibrate-rig --algo sha256`.

**Why the returns verdict is still valid during the transition:** the returns-based
verdict (claim 1) is invariant to the absolute energy scale — constant multipliers cancel
in log-returns. The multi-algorithm extension only affects *level* claims (joules/Qi,
price-to-cost ratio). The returns verdict is effectively "Qi versus difficulty"; adding
workshare difficulty to the effective difficulty series does not change the qualitative
result, only the level.

**What remains an open risk:** the current RPC response does not expose an explicit
algorithm field on workshares — the SHA-256 vs Scrypt distinction requires parsing the
raw `data` blob (AuxPoW header). Until the RPC is upgraded, `fetch_data.py` splits
workshares into two buckets by heuristic (KawPoW workshares have a `mixHash` field;
SOAP workshares do not). The `soap_ws` bucket is treated as SHA-256 by default. This
is noted in every output that uses workshare data, and the limitation is tracked in
the `fetch_workshare_difficulty` docstring.

**Merge-mining and ASIC coverage:** the workshare mechanism means the same hardware
that secures Bitcoin Cash or Litecoin also contributes to Quai's energy anchor — without
any additional energy expenditure. This is a strength of the thesis, not a weakness: the
energy peg is anchored to a broader, more diverse hardware base than KawPoW alone.

## (k) The dual-revenue model (Claim 6) assumes miners can run inference simultaneously — that's not how mining works

**Objection:** Mining requires 100% GPU utilisation. You can't serve inference on a GPU that's already mining. The dual-revenue model is physically impossible.

**Treatment here — three valid scenarios, one of which requires no time-sharing:**

The objection is partially correct: a GPU running KawPoW at full utilisation cannot simultaneously run Ollama inference at full capacity. Claim 6 does not assert that both workloads run at 100% simultaneously. The dual-revenue model is valid in three real scenarios:

1. **Workshare submission is probabilistic, not continuous.** KawPoW mining is a hash lottery — a miner submits a workshare when they find a hash below the workshare threshold. Between submissions, the GPU is hashing. Inference can be interleaved during the microseconds between hash evaluations, though at the cost of reduced throughput on both workloads. This is the weakest version of the claim.

2. **The crossover daemon model.** The `tools/crossover-daemon/` daemon switches the GPU between mining and inference based on live revenue. When inference demand is high, the GPU serves inference; when demand is low, it mines. The workshare rewards in Claim 6 represent the mining revenue during idle inference periods, not simultaneous operation. The crossover daemon is the operational complement to Claim 6.

3. **ASIC workshares + GPU inference (the cleanest version).** Under Project SOAP, SHA-256 ASICs and Scrypt ASICs submit workshares to Quai blocks. A node that runs a SHA-256 ASIC (mining BCH/BTC and submitting workshares to Quai) alongside a GPU (serving inference) achieves true simultaneous dual-revenue without any GPU time-sharing. The ASIC handles workshare submission; the GPU handles inference. Claim 6's sensitivity table includes ASIC-class hashrates precisely because this is the most physically realistic version of the model.

**What Claim 6 actually tests:** whether the workshare reward stream is economically non-trivial (≥ 5% of energy cost) for a reference rig — not whether both workloads run simultaneously at full capacity. The break-even utilisation metric in the output directly quantifies how much inference capacity is needed to cover the remaining energy cost after workshare subsidies.

## (l) "Bitcoin miners will never point hashrate at Quai — the SOAP incentive is too small"

**Objection:** Bitcoin's SHA-256 hashrate (~800 EH/s) is orders of magnitude larger than
Quai's current difficulty. The QUAI reward from submitting a workshare is negligible
relative to the BTC block reward. No rational Bitcoin miner will implement SOAP support
for such a small marginal gain.

**Treatment here:** The objection is correct about the current economics at the individual
miner level, but misidentifies the mechanism. SOAP adoption does not require individual
miners to change their behaviour — it requires **mining pool software** to add SOAP
workshare submission as a background process. The overhead per hash is negligible (one
additional RPC call per found workshare); the question is whether the aggregate QUAI
reward across the pool is worth the engineering cost of implementation.

At 0.01% of Bitcoin's hashrate (0.08 EH/s), the workshare revenue in Qi/day already
dwarfs the GPU inference energy cost for a reference node (see `results/claim6.md`).
This means the incentive threshold for pool adoption is low — not "enough to change
miner behaviour" but "enough to justify a pool software update."

Furthermore, the SOAP mechanism has a compounding property: as QUAI appreciates (driven
by buybacks from BCH/LTC block rewards flowing to the protocol), the QUAI reward per
workshare increases in USD terms, making the economics progressively more attractive.

**What P7 tests:** not whether Bitcoin miners will adopt SOAP, but whether any ASIC
participation is growing at all. A positive P7 result (SOAP fraction growing at ≥1 pp/quarter)
is a falsifiable early signal that the flywheel is turning, even if total adoption remains
small. A negative result is equally informative — it would suggest the QUAI reward is
currently insufficient to motivate pool implementation, which is useful data for the
Quai Network team.

**Merge-mining precedent:** Namecoin has been merge-mined with Bitcoin since 2011.
Approximately 50–60% of Bitcoin's hashrate currently merge-mines Namecoin, despite NMC
having negligible USD value. The barrier to merge mining is pool software support, not
miner incentive — and that barrier was cleared for Namecoin with far less economic
justification than SOAP offers.
