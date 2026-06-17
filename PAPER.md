# Is Qi Energy Money? (skeleton)

> Status: skeleton. Results sections are wired to generated artifacts in
> `results/` and remain empty until real data is pulled and PREDICTIONS.md
> thresholds are frozen. Nothing here is a finding yet.

## Abstract

We test whether Qi, the proof-of-work-mined token of Quai Network, functions
as *energy money* — a monetary unit whose **market price** tracks the energy
cost of its production — and whether, in consequence, Qi is the natural unit
of account for energy-marginal computation. We distinguish the protocol-level
coupling of Qi emission to network difficulty, which holds by construction
and is not evidence, from market-level coupling, which is the hypothesis
under test against an explicit null (Qi as generic crypto beta, proxied by
BTC). We measure joules-per-token for open-model inference on real hardware
under a stated measurement boundary, derive a Qi-per-million-tokens index
from energy content, and demonstrate integer-exact settlement at the
joule-derived rate. Findings: [headline result, whichever direction it
points — including, if applicable, that Qi's market is too thin for the
question to be testable]. Scope: the unit-of-account claim is made only for
compute whose marginal cost is dominated by electricity; we estimate that
fraction across hardware classes and do not extend the claim to
capex-dominated datacenter compute.

## 1. Thesis

Qi, the token of Quai Network, is mined by proof-of-work: every unit enters
circulation by expending measurable energy. The thesis is that Qi's market
value tracks the energy cost of its production — that Qi is *energy money* —
and that for compute whose marginal cost is almost purely energy
(depreciated GPUs, the global pool of idle mining hardware), Qi is therefore
the structurally correct unit of account, where USD or BTC pricing of the
same compute inherits those denominations' volatility.

QiCompute asks whether Qi can become the unit of account for machine
intelligence because all machine intelligence begins as energy consumed by
computation. The chain's role is deliberately narrow: Quai secures the money
layer with proof-of-work; compute is measured and priced *above* the chain.
Nothing here proposes AI workloads as consensus, or useful work as a
replacement for mining — useful AI work should be paid for *with* Qi, not
used to replace Quai's proof-of-work.

### 1.1 By construction vs by market

Two couplings must not be conflated, and this paper tests only the second:

- **Protocol-level coupling (by construction).** Quai's emission schedule
  and difficulty adjustment mechanically relate Qi issuance to hashrate and
  hence to energy expended. This is mechanics — true by design, shared in
  kind with every proof-of-work asset, and **not a finding**.
- **Market-level coupling (the hypothesis).** Whether Qi's *exchange price*
  tracks the modeled energy cost of production is not guaranteed by any
  protocol: Bitcoin's identical mechanics coexist with market prices that
  spend years far from production cost. Claim 1's regressions therefore run
  on market price with BTC beta as the built-in null.

A reader who takes a claim-1 confirmation as "the protocol works as
designed" has misread the result; the protocol working as designed is the
premise.

### 1.2 The corollary

Qi prices the energy **input** of compute, not the output. Qi/token must
fall as joules/token falls with hardware and software efficiency; only
Qi/joule can be the stability claim. Every chart in this paper is
disciplined by that distinction, and a stable multi-year Qi/token series
would contradict the corollary rather than support the thesis.

### 1.3 Scope

The unit-of-account claim covers **energy-marginal compute**: hardware whose
marginal cost of one more unit of work is dominated by electricity (sunk-
capex consumer GPUs on power the operator already buys — at the margin,
~100% energy). It is *not* claimed for capex-dominated compute: an amortized
datacenter H100's cost is roughly 7% energy, and no result here extends to
it. Qi prices the energy component of compute, never the whole cost. The
claim is also conditional on testability: Qi trades thinly, and below a
pre-registered liquidity threshold (PREDICTIONS.md) the market price is
treated as noise and the honest result is "untestable at current
liquidity".

## 2. Lineage

The idea that money should be denominated in energy is old and repeatedly
reinvented:

- **Henry Ford's "energy dollar" (1921–22).** Around the Muscle Shoals
  proposal, Ford argued for currency issued against kilowatt-hours of
  generating capacity instead of gold — value rooted in productive energy
  rather than scarcity convention.
- **Technocracy's energy certificates (1930s).** Howard Scott and M. King
  Hubbert's Technocracy movement proposed accounting in ergs/joules
  outright: income as a claim on a share of continental energy production.
- **Buckminster Fuller's kilowatt-hour currency.** Fuller argued
  ("energy accounting", *Critical Path*, 1981) that the kWh is the only
  non-arbitrary unit of cost, and that accounts kept in energy would expose
  real wealth creation.

All three lacked a mechanism: nothing tied the certificate to the joule
except institutional promise. Proof-of-work supplies a mechanism candidate —
issuance that *cannot happen* without energy expenditure, with difficulty as
the coupling. Whether that coupling actually holds in market prices is an
empirical question, hence this paper. (The Bitcoin literature on cost-of-
production pricing is the cautionary tale: see OBJECTIONS.md (e).)

## 3. Method

- **Claim 1 (peg tracking, market level):** daily Qi/USD (source: see
  `research.yaml`), Quai network difficulty, and a modeled cost of
  production (difficulty → joules/Qi for a reference RTX 3090 ×
  global-marginal $/kWh). Qi log-returns regressed on modeled-cost returns
  and, as the null, on BTC returns. Verdict rules, minimum sample size, and
  the liquidity threshold below which no verdict is issued are
  pre-registered in PREDICTIONS.md.
- **Claim 2 (unit of account):** fixed bundles (1 kWh; 1M tokens) priced
  daily in USD, BTC, Qi via market rates; rolling 30-day volatility
  compared.
- **Claim 3 (ground truth):** joules/token measured on real hardware
  (NVML power draw during Ollama inference), public schema, multiple
  contributors.
- **Claim 4 (settlement):** integer micro-Qi escrow/settlement with receipt
  emission; mock ledger pending Quai testnet tooling.
- **Claim 5 (K-Quai controller directionality):** on-chain `woHeader.lock`
  (miner token choice) and `header.exchangeRate` sampled from every block.
  Tests whether miner Qi-election fraction leads exchange-rate adjustments
  (P5a/P5b) and whether the market-implied rate tracks the on-chain rate
  within ±20% (P5c). Robustness check: the thesis holds regardless of miner
  preference because QUAI and Qi are convertible at the protocol rate; P5
  tests controller correctness, not thesis precondition.
- **Claim 6 (dual-revenue model):** models the economics of a GPU that
  simultaneously mines Quai (submitting workshares) and serves inference
  (earning customer payment). Workshare rewards are standard KawPoW partial
  proofs — not AI outputs as consensus. Pre-registered threshold: workshare
  rewards cover ≥ 5% of energy cost at current network difficulty.

Reproduction: `python3 reproduce.py` regenerates everything from cached raw
pulls (`data/`). No smoothing; thin data reported, never interpolated.

## 4. Results

### 4.1 Claim 1 — peg tracking

![Qi price vs modeled energy cost](results/claim1_peg.png)

Stats: `results/claim1_stats.json` · Narrative: `results/claim1.md`

[Empty until data pull. Must report: verdict, both R², betas, t-stats,
sample size, liquidity context, and the $0.04–$0.20/kWh sensitivity check
from OBJECTIONS.md (b).]

### 4.2 Claim 2 — unit-of-account stability

![Stability by denomination](results/claim2_stability.png)

Stats: `results/claim2_stats.json` · Narrative: `results/claim2.md`

[Empty until data pull. Qi/joule is the claim; Qi/token presented with the
corollary gap explained.]

### 4.3 Claim 3 — joules/token

Dataset: `measurements.db` (schema in `benchmark.py`)

[Empty until first hardware submissions. Report median joules/token by
model class and hardware generation; year-over-year decline rate vs
PREDICTIONS.md P3.]

### 4.4 Claim 4 — settlement

Receipt example: `results/receipt_demo-job-1.json`

[Conservation and idempotency results over the randomized-cycle test in
PREDICTIONS.md P4; settlement layer status (mock vs testnet).]

### 4.5 Claim 5 — K-Quai controller directionality

Stats: `results/claim5_stats.json` · Narrative: `results/claim5.md`

[Empty until ≥ 90 days of on-chain `woHeader.lock` and `header.exchangeRate`
data are accumulated. Must report: P5a correlation and direction, P5b
best-lag and leading-signal flag, P5c market/on-chain ratio and consecutive
deviation days. If P5c is `insufficient_data` due to thin QI market price,
report that explicitly — it is not a failure. Report the mean Qi-election
fraction and mean on-chain exchange rate as context regardless of verdict.]

**Interpretation note:** P5 does not test whether miners choose Qi over QUAI.
Because the two tokens are convertible at the protocol rate, the energy-money
thesis holds regardless of miner preference. P5 tests whether the K-Quai
controller correctly transmits miner preference signals into exchange-rate
adjustments — a protocol-correctness check, not a thesis prerequisite.

### 4.6 Claim 6 — workshare-for-inference dual-revenue model

Stats: `results/claim6_stats.json` · Narrative: `results/claim6.md`

[Empty until real difficulty and joules/token data are available. Must report:
workshare coverage fraction vs the pre-registered 5% threshold, break-even
utilisation fraction, expected workshares/day for the reference rig, and the
full sensitivity table across hashrate and difficulty multipliers.]

**Interpretation note:** Claim 6 models the economics of a GPU that
simultaneously mines Quai and serves inference. The workshare rewards are
standard KawPoW partial proofs — not AI outputs used as consensus. The claim
is that the dual-revenue model is economically non-trivial at current network
parameters, not that workshare rewards alone are sufficient to run inference
profitably. The crossover daemon in `tools/crossover-daemon/` is the
operational complement: it switches between mining and inference based on live
revenue, while Claim 6 models the case where both run simultaneously.

### 4.7 Claim 7 — SOAP adoption rate as energy anchor leading indicator

Stats: `results/claim7_stats.json` · Narrative: `results/claim7.md`

[Empty until 90+ days of post-SOAP-launch (Dec 2025) workshare data are available.
Must report: SOAP fraction trend (slope in pp/quarter), R² of the OLS fit, baseline
and latest SOAP fraction, and the verdict against the pre-registered thresholds in
`research.yaml → claim7`.]

**Interpretation note:** Claim 7 is a leading indicator, not a peg test. A positive
result (SOAP fraction growing at ≥1 pp/quarter) is evidence that the energy anchor
is broadening — more diverse hardware is contributing to Qi's energy backing. It
does not establish that Bitcoin-scale hashrate will flow to Quai; it tests only whether
any ASIC participation is measurably growing. The Bitcoin-scale scenarios in
`results/claim6.md` are a model of consequences at each adoption level; Claim 7 is
the empirical instrument that tracks whether those scenarios are becoming reality.

**Merge-mining context:** Namecoin has been merge-mined with Bitcoin since 2011, with
~50–60% of Bitcoin's hashrate participating despite NMC having negligible USD value.
The barrier to SOAP adoption is pool software support, not miner incentive — a point
addressed in OBJECTIONS.md (l).

## 5. Objections and limitations

Incorporated by reference: OBJECTIONS.md (a)–(l). The conclusion section may
not use causal language ("anchors", "is caused by") for claim 1 —
"tracks"/"fails to track" only — per objection (e).

## 6. Conclusion

[Empty. Written after results; published with the same prominence either
way.]

## Appendix A — reproduction

```bash
pip install -r requirements.txt
python3 reproduce.py          # fetch + analyze + results/REPORT.md
python3 -m unittest           # 30+ deterministic tests
```

## Appendix B — data provenance

Every series in `data/*.json` carries its source URL and fetch timestamp,
with a CSV mirror for inspection. Synthetic fixtures live only in
`data/sample/` and are labeled in every output they touch.
