# QiCompute Architecture

QiCompute is a local-first prototype for private distributed inference markets. It models the control plane and accounting path before real networking or chain settlement exists.

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

## Privacy Model

Raw prompts are not stored in customer jobs, receipts, logs, or summaries. The local Ollama runtime may receive a prompt for execution, but QiCompute stores prompt hashes, output hashes, token counts, timing, and verification metadata. Raw model output is not persisted.

Cluster transport preserves the same default. Worker receipts contain output hashes and accounting metadata, not raw model output. Prompt transfer is intentionally constrained to local test payloads until a stronger privacy design exists.

## Local LAN Transport

`transport.py` uses the Python standard library only. Worker messages are signed with a shared-secret HMAC over timestamp, nonce, and canonical request body hash.

The controller rejects missing signatures, expired timestamps, duplicate nonces, tampered bodies, and invalid signatures. This is a development boundary for trusted LAN testing, not public internet infrastructure.

Accepted nonces are persisted in SQLite so replayed requests fail even after a controller object restart. Expired nonce records can be pruned.

## Worker Enrollment

Cluster workers can be enrolled before they authenticate. Enrollment records are stored as `pending`, `active`, or `revoked`. Raw worker secrets are not stored; the controller stores only a shared-secret hash. In local demos, `cluster.allow_dev_shared_secret` can enable the configured development secret as a fallback. Main config keeps that fallback disabled.

## Job Leases

The controller assigns jobs with a lease ID and lease expiration. Receipts must include the matching lease ID. Expired leases are requeued so disappeared workers do not permanently lock jobs.

## Controller Snapshots

`snapshot.py` exports a deterministic controller snapshot for future failover and decentralization work. It includes worker summaries, active jobs, outstanding leases, recent events, audit logs, and active epoch state without raw prompts or raw outputs.

## Mining Fallback Philosophy

Inference is the primary work mode. Mining fallback exists to keep GPU workers economically active when inference demand is unavailable. Mining shares are accounting inputs for future block reward distribution and do not directly increase balances.

## Useful-Work Philosophy

QiCompute treats useful compute as energy-aware, receipt-backed work that must pass verification before payout eligibility. The long-term settlement path is:

```text
Energy -> Compute -> Useful Work -> Verification -> Settlement
```
