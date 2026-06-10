# QiCompute Architecture

QiCompute is a local-first prototype for private distributed inference markets. It models the control plane and accounting path before real networking or chain settlement exists.

## Current Status

QiCompute v0.1.0 is an experimental MVP. It demonstrates a local/LAN architecture for private inference execution, useful-work verification, settlement accounting, and operator tooling.

The architecture is intentionally protocol-shaped but not decentralized yet. Current cluster mode assumes a trusted LAN controller. Public networking, blockchain settlement, production cryptography, and production consensus are future work.

```text
customer job
-> routing
-> daemon/runtime
-> receipt
-> challenge verification
-> committee verification
-> epoch settlement
```

The LAN cluster skeleton adds an explicit controller/worker boundary:

```text
controller node
-> worker heartbeat
-> worker capability sync
-> job assignment
-> worker daemon execution
-> receipt submission
-> verification
-> epoch settlement
```

```mermaid
flowchart LR
    A[Customer Job] --> B[Router]
    B --> C[Worker Daemon]
    C --> D[Runtime Adapter]
    D --> E[Worker Receipt]
    E --> F[Challenge Verification]
    F --> G[Committee Verification]
    G --> H[Payout Event]
    H --> I[Settlement Epoch]
```

## Routing Layer

The router chooses from locally registered workers. It scores workers using online status, model support, reputation, region preference, VRAM, latency, energy efficiency, failure rate, load, and price constraints. Route decisions are stored as audit logs.

In cluster mode, the controller owns the worker registry and job queue. Workers send signed heartbeats and capability claims, then poll for the next assigned job.

## Runtime Layer

The daemon polls locally assigned jobs, moves them to running, executes the selected runtime, emits a runtime result, creates a receipt, and updates job status. Runtime adapters currently include simulated, subprocess, Ollama, and placeholders for Ollama/llama.cpp-style integrations.

In worker-node mode, `daemon.py --cluster-worker` registers with the controller, polls `/job/next`, executes locally, and submits only the receipt payload back to the controller.

## Trust Layer

Receipts are deterministically hashed and locally verified. Challenge verification checks useful-work-shaped metadata, and committees simulate future multi-worker validation. Rejected or disputed results block payout eligibility and reduce reputation.

## Settlement Layer

Accepted work creates local payout events. Settlement epochs batch those payout events into deterministic summaries with energy totals, token totals, challenge outcomes, committee outcomes, and worker totals. Balances derive from settled payout events only.

Cluster receipts follow the same rule: controller-accepted receipts create local payout events and epoch summaries; rejected receipts do not update payable balances.

## Marketplace Accounting

Customer accounts separate spendable and escrowed Qi. Jobs reserve estimated funds before routing. Verified successful work settles escrow into worker payable Qi plus marketplace fee, with unused escrow refunded to the customer. Failed, rejected, expired, or disputed jobs refund escrow and do not increase worker payable balance.

Worker accounts track earned, payable, disputed, rejected, and refunded Qi. Marketplace treasury totals track fees, worker payouts, refunds, disputed volume, and settled volume. `accounting_checks.py` reconciles these local ledgers against job escrow records and paid inference jobs.

This is a local deterministic economic simulation. QiCompute is not a blockchain, wallet, token transfer system, or payment processor.

## Agent Economic Participation

Qi is mined; QiCompute moves Qi.

Qi is only mined. QiCompute does not mint Qi, and autonomous agents do not receive minted Qi by virtue of being agents.

Architecture framing:

```text
Qi = mined currency / settlement asset
QiCompute = inference marketplace using Qi as payment
```

Agents use the same economic layer as humans and organizations. An agent can acquire Qi by mining with authorized GPU hardware, earning existing Qi from customers by serving verified inference, earning existing Qi through verification or infrastructure roles, or receiving Qi from a human/operator account.

`agent_accounts` records local agent balances:

- `mined_qi`: Qi obtained through the mining path.
- `earned_qi`: existing Qi earned from verified marketplace services.
- `spent_qi`: Qi spent on customer jobs.
- `qi_balance`: spendable local balance after escrow reservations and refunds.

Agent mining income is recorded as externally-recorded mined Qi from authorized mining activity. It is not QiCompute issuance and does not create a second issuance mechanism inside QiCompute. Agent job escrow reserves spendable Qi before job routing, spends it after successful completion, and refunds it after failed work.

Agent direct worker credits are simulation-only in v0.1.0. They model a worker-owned agent earning from a verified receipt, with duplicate receipt protection, but they do not replace reconciled marketplace settlement. The canonical reconciled path remains customer escrow settlement through `settle_job_escrow`, which updates worker payable accounting and marketplace treasury totals.

One currency. One issuance mechanism. Multiple ways to earn and spend it.

## Autonomous Compute Economy

Qi creates currency. QiCompute allocates currency. Agents decide how to earn and spend it.

Idle hardware mines. Useful hardware earns. Agents choose which is more profitable.

The autonomous economy layer is simulation and policy logic only. `economic_scheduler.py` compares deterministic opportunities for mining, inference, verification, routing, and idle capacity. `market_demand.py` models queued jobs, waiting customers, latency, revenue, and utilization pressure. `mining_economics.py` estimates local mining profitability without external APIs. `crossover.py` reports the demand threshold where inference becomes more profitable than mining.

No autonomous economy module introduces blockchain integration, staking, governance tokens, slashing, yield farming, smart contracts, public networking, or new issuance.

## Economic Research Layer

The economic research layer asks whether the marketplace incentives work:

```text
customer demand -> provider choice
mining fallback -> price floor
worker utilization -> inference premium
agent strategy -> market share and survival
regional conditions -> routing and profitability
market volume -> Qi circulation or hoarding
```

`customer_demand.py` scores QiCompute, centralized AI APIs, GPU clouds, and self-hosting for different customer types. `market_pricing.py` keeps mining profitability as the floor so inference must pay more than idle mining fallback to attract workers. `federation_simulation.py` models controller handoff, verifier handoff, trust boundaries, and reconciliation without implementing public networking.

`agent_competition.py`, `reputation_dynamics.py`, `regional_market.py`, `agent_to_agent.py`, and `monetary_simulation.py` model strategy competition, reputation convergence, regional profitability, agent-to-agent trade, and monetary circulation. `economy_dashboard.py` aggregates those simulations into customer choice, pricing crossover, agent competition, regional routing, monetary circulation, risks, and opportunities.

Qi creates currency through mining. QiCompute allocates currency through useful compute markets. Agents and humans participate in the same economic layer.

## Threat Model

QiCompute now models adversarial local marketplace behavior: malicious workers, malicious customers, replay attackers, spam, escrow griefing, malicious verifiers, and colluding committees.

Receipt replay resistance is enforced before settlement. Duplicate settled receipt hashes and stale receipts after refund/failure are rejected and logged as audit events. Invoice hashes are deterministic and can be verified for mutation detection.

Escrow abuse resistance is configurable through minimum job escrow, maximum outstanding customer escrow, and escrow expiry cleanup. Rate-limit events track customer submission spam, receipt spam, verifier spam, and failed-auth bursts.

Committee consensus records abuse metadata: disagreement ratio, repeated verifier pair frequency, same-operator clustering, and a collusion suspicion score. These are simulation signals only; there is no staking, slashing, or production-grade Sybil resistance yet.

## Performance Layer

The performance layer is intentionally local and dependency-free:

```text
synthetic workers -> synthetic jobs -> routing/leases -> simulated runtime -> verification -> settlement -> metrics
```

`perf.py` provides timers, percentile calculation, metric accumulation, query timing, and bottleneck summaries. `load_test.py` runs deterministic synthetic controller load and reports throughput, latency percentiles, worker utilization, DB size, settlement totals, refund totals, and abuse counters. `bottleneck_report.py` summarizes routing, DB write, verification, committee, settlement, and execution time.

SQLite indexes are installed with `CREATE INDEX IF NOT EXISTS` for the local hot paths: queued/routed jobs, assigned workers, leases, receipts, payout events, worker online/reputation scans, routing audit lookup, cluster event recency, and nonce expiry. This improves the LAN prototype but does not change the long-term need for a more distributed storage and coordination model.

## Privacy Model

Strict mode is the default. Raw prompts are not stored in customer jobs, receipts, logs, audit trails, snapshots, or summaries. The local Ollama runtime may receive a prompt transiently for execution, but QiCompute stores prompt hashes, output hashes, byte counts, token counts, timing, energy estimates, and verification metadata. Raw model output is not persisted.

Private job payloads use a local prototype envelope with `encrypted_payload`, `payload_nonce`, and `payload_hash`. This is not audited cryptography and is not production E2E encryption. It exists to shape the controller/worker boundary before stronger cryptography is added.

Cluster transport preserves controller-blind prompt handling where practical. The controller routes by metadata and hashes, while worker runtimes decrypt only inside the local execution path and submit receipts with hashes and accounting metadata.

## Local LAN Transport

`transport.py` uses the Python standard library only. Worker messages are signed with a shared-secret HMAC over timestamp, nonce, and canonical request body hash.

The controller rejects missing signatures, expired timestamps, duplicate nonces, tampered bodies, and invalid signatures. This is a development boundary for trusted LAN testing, not public internet infrastructure.

Accepted nonces are persisted in SQLite so replayed requests fail even after a controller object restart. Expired nonce records can be pruned.

## Worker Enrollment

Cluster workers can be enrolled before they authenticate. Enrollment records are stored as `pending`, `active`, or `revoked`. Raw worker secrets are not stored; the controller stores only a shared-secret hash. In local demos, `cluster.allow_dev_shared_secret` can enable the configured development secret as a fallback. Main config keeps that fallback disabled.

`enroll.py` provides the operator workflow for creating, activating, revoking, listing, and exporting worker config snippets.

## Job Leases

The controller assigns jobs with a lease ID and lease expiration. Receipts must include the matching lease ID. Expired leases are requeued so disappeared workers do not permanently lock jobs.

Worker clients can process multiple leased jobs concurrently up to configured runtime capacity. Runtime failures are isolated per job, and stale or duplicate receipts do not create a second payout.

## Controller Snapshots

`snapshot.py` exports a deterministic controller snapshot for future failover and decentralization work. It includes worker summaries, active jobs, outstanding leases, recent events, audit logs, and active epoch state without raw prompts or raw outputs.

## Mining Fallback Philosophy

Inference is the primary work mode. Mining fallback exists to keep GPU workers economically active when inference demand is unavailable. Mining shares are accounting inputs for future block reward distribution and do not directly increase balances.

## Useful-Work Philosophy

QiCompute treats useful compute as energy-aware, receipt-backed work that must pass verification before payout eligibility. The long-term settlement path is:

```text
Energy -> Compute -> Useful Work -> Verification -> Settlement
```
