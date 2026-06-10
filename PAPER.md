# Is Qi Energy Money? (skeleton)

> Status: skeleton. Results sections are wired to generated artifacts in
> `results/` and remain empty until real data is pulled and PREDICTIONS.md
> thresholds are frozen. Nothing here is a finding yet.

## Abstract

[To write last. One paragraph: thesis, method, headline result — whichever
direction it points.]

## 1. Thesis

Qi, the token of Quai Network, is mined by proof-of-work: every unit enters
circulation by expending measurable energy. If its market value tracks the
energy cost of its production, Qi is *energy money*, and for compute whose
marginal cost is almost purely energy — depreciated GPUs, the global pool of
idle mining hardware — it is the structurally correct unit of account:
Qi-per-joule stable by construction, where USD or BTC pricing of the same
compute inherits those denominations' volatility.

The corollary that disciplines every chart in this paper: Qi prices the
energy **input** of compute, not the output. Qi/token must fall as
joules/token falls with efficiency; only Qi/joule can be the stability
claim.

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

- **Claim 1 (peg tracking):** daily Qi/USD (source: see `research.yaml`),
  Quai network difficulty, and a modeled cost of production
  (difficulty → joules/Qi for a reference RTX 3090 × global-marginal $/kWh).
  Qi log-returns regressed on modeled-cost returns and, as the null, on BTC
  returns. Verdict rules and minimum sample size pre-registered in
  PREDICTIONS.md.
- **Claim 2 (unit of account):** fixed bundles (1 kWh; 1M tokens) priced
  daily in USD, BTC, Qi via market rates; rolling 30-day volatility
  compared.
- **Claim 3 (ground truth):** joules/token measured on real hardware
  (NVML power draw during Ollama inference), public schema, multiple
  contributors.
- **Claim 4 (settlement):** integer micro-Qi escrow/settlement with receipt
  emission; mock ledger pending Quai testnet tooling.

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

## 5. Objections and limitations

Incorporated by reference: OBJECTIONS.md (a)–(e). The conclusion section may
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
