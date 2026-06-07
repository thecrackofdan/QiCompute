# Architecture Audit

## Scope

This audit reviews QiCompute as a local-first v0.1.0 research prototype. It does not assume public networking, chain settlement, wallets, production cryptography, or production consensus exist today.

## Strongest Design Decisions

Low risk:

- Clear separation between mining issuance and compute marketplace settlement. The docs and code consistently say Qi is mined and QiCompute moves Qi.
- Local accounting is explicit. Customer accounts, job escrows, worker accounts, payout events, treasury totals, invoices, and epochs are separate concepts.
- Privacy defaults are concrete. Raw prompts and raw outputs are avoided in jobs, receipts, logs, snapshots, and summaries.
- Deterministic tests and simulations make assumptions inspectable. This is appropriate for research before deployment.
- Failure paths are first-class. Duplicate receipts, stale receipts, expired leases, rejected work, refunds, disputed work, and replayed transport nonces have tests.

Medium risk:

- The controller/worker boundary is well shaped but still centralized. That is acceptable for an MVP but should not be confused with decentralization.
- Agent accounting is useful for research, but direct agent worker credit remains simulation-only and separate from canonical escrow/treasury settlement.
- Committee verification is useful as a design sketch, but its current trust and Sybil model is only simulated.

## Over-Engineered Areas

Medium risk:

- The repo has many modules for a prototype. The boundaries are mostly understandable, but the number of economic and simulation files can make it harder to tell which outputs are evidence and which are placeholders.
- Agent economy modeling is broad relative to measured demand. The project now models competition, reinvestment, reputation, regions, and monetary velocity before validating whether any customer segment will pay.
- Federation, committee, and decentralization simulations may imply more maturity than exists if read without the current-state caveats.

Low risk:

- Extensive documentation is not a problem, but several docs repeat the same principles. This helps clarity but creates maintenance drift risk.

## Under-Specified Areas

High risk:

- Real Qi mining authorization is not specified. The prototype records mined Qi locally but does not define how authorized mining hardware is proven.
- Real settlement is absent. There is no wallet, payment rail, blockchain settlement, or enforceable transfer mechanism by design.
- Customer demand is assumed through deterministic scoring, not observed behavior.
- Verification quality is not benchmarked against real adversarial model outputs or real model execution variance.
- Legal and privacy obligations are not mapped to specific jurisdictions or data classes.

Medium risk:

- Operator economics need real energy, hardware depreciation, model serving cost, and utilization measurements.
- Reputation recovery and committee honesty are modeled but not validated against realistic attack rates.
- Regional routing preference is simulated without real latency, supply, demand, or privacy law data.

## Simulation-Only Areas

High risk:

- Economic dashboard outputs.
- Customer provider choice.
- Dynamic pricing and mining fallback floor.
- Multi-agent competition.
- Monetary circulation and hoarding.
- Federation handoff and reconciliation.
- Reputation convergence.
- Agent-to-agent trade.

Medium risk:

- Useful-work committees.
- Agent direct worker credits.
- Mining profitability estimates.
- Reinvestment and capacity growth.

Low risk:

- Demo and load-test summaries are useful local validation, but they are not market evidence.

## Difficult To Productionize

High risk:

- Moving from trusted LAN controller to adversarial public network.
- Proving useful inference without exposing private prompts or outputs.
- Preventing Sybil attacks in worker registration, verifier committees, and reputation.
- Binding local accounting to real Qi movement without introducing a second issuance path.
- Meeting enterprise privacy, audit, data residency, and breach-response requirements.

Medium risk:

- Operating reliable model runners across heterogeneous hardware.
- Pricing jobs accurately across models, regions, latency classes, energy cost, and worker quality.
- Maintaining deterministic accounting while adding concurrency and distributed coordination.

## Risk Summary

Low risk:

- Local deterministic accounting.
- Test categorization and release checks.
- Clear non-goals around wallets, chains, staking, and governance.

Medium risk:

- Module sprawl.
- Documentation drift.
- Agent economy breadth before external validation.

High risk:

- Demand assumptions.
- Production trust model.
- Real settlement.
- Real verification strength.
- Decentralization gap.
