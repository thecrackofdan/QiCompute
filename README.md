# Qi Compute Pool Worker Prototype

Local Python prototype for a unified Qi compute/mining pool worker. It runs on a GPU rig and chooses inference work when a local job is available, otherwise it falls back to mining mode.

This MVP has no smart contracts and no real payout rail. It records local receipts, telemetry, estimated energy usage, output, and estimated Qi owed in SQLite.

## Components

- `worker.py`: CLI entrypoint and config loading.
- `scheduler.py`: mode selection, placeholder launchers, accounting.
- `telemetry.py`: GPU telemetry via `nvidia-smi`, with fallback watts when unavailable.
- `receipts.py`: local job receipt format.
- `verifier.py`: local inference receipt validation.
- `challenges.py`: local proof-of-useful-work challenge simulation.
- `committees.py`: local verification committee consensus simulation.
- `epochs.py`: settlement epoch batching and summaries.
- `registry.py`: local worker registry helpers.
- `router.py`: local inference job routing.
- `reputation.py`: worker reputation updates.
- `pricing.py`: local marketplace pricing estimates.
- `envelopes.py`: signed job envelope-shaped structures with placeholder signatures.
- `capabilities.py`: worker capability claim structures.
- `customer_receipts.py`: customer-facing job receipt structures.
- `failures.py`: standardized local failure codes.
- `lifecycle.py`: customer job state transitions.
- `retry.py`: local retry policy helpers.
- `adversary.py`: deterministic bad-worker behavior simulation.
- `simulation.py`: local marketplace simulation.
- `stress_simulation.py`: deterministic marketplace stress simulation.
- `market.py`: local marketplace CLI.
- `db.py`: SQLite schema and persistence.
- `config.yaml`: local worker configuration.

## Requirements

- Ubuntu with Python 3.10+.
- NVIDIA drivers with `nvidia-smi` for real GPU telemetry.
- Optional: `PyYAML`. The worker includes a small fallback parser for the provided `config.yaml`.

## Quick Start

Run one scheduler cycle:

```bash
python3 worker.py --once
```

If there are no jobs in `jobs/`, the worker enters placeholder mining mode for `mining.cycle_seconds`, estimates shares, records a receipt, and exits.

Check estimated local Qi balance:

```bash
python3 worker.py --balance
```

This prints both settled payout balance and estimated receipt total. Settled balance is derived only from accepted payout events.

Show recent receipts:

```bash
python3 worker.py --recent 5
```

Show recent payout events:

```bash
python3 worker.py --payouts 5
```

Simulate a Qi block found by the pool and distribute the block reward over the configured PPLNS window:

```bash
python3 worker.py --settle-block-reward 100 --block-hash qi-block-001
```

Run smoke tests:

```bash
python3 -m unittest -v
```

## Marketplace Prototype

The local marketplace layer models:

```text
customer job -> router -> selected worker -> receipt -> verification -> reputation -> settled payout
```

Register the local worker:

```bash
python3 market.py --register-worker
```

Show online workers:

```bash
python3 market.py --workers
```

Submit a simulated customer job. Raw prompts are not stored; only a placeholder prompt hash is recorded.

```bash
python3 market.py --submit-job --model llama-3.1-8b --input-tokens 100 --output-tokens 500
```

Route queued jobs:

```bash
python3 market.py --route-jobs
```

Show queued jobs or reputation:

```bash
python3 market.py --queued-jobs
python3 market.py --reputation
```

Run a local marketplace simulation:

```bash
python3 market.py --simulate
```

Run a deterministic stress simulation:

```bash
python3 market.py --stress-sim
```

Routing considers online status, model support, reputation, region preference, VRAM, latency, energy efficiency, and failure rate. This is local route planning only; no network calls are made.

## Marketplace Protocol Shape

QiCompute now models the local protocol objects needed for a future distributed marketplace:

- Job envelopes: customer intent with job ID, model, prompt hash, token counts, max price, expiry, nonce, and placeholder signature. Raw prompts are not stored.
- Worker capability claims: supported models, GPU profile, power capacity, privacy features, benchmark placeholder, and placeholder signature.
- Routing audit logs: every route decision can be recorded with selected worker, score, alternatives, reason, failure code, and router version.
- Customer receipts: customer-facing receipt built from the customer job, route decision, worker receipt, and verification result.
- Failure codes: standardized rejection reasons such as `MODEL_NOT_SUPPORTED`, `INVALID_ENVELOPE`, `INVALID_CAPABILITY_CLAIM`, `VERIFICATION_FAILED`, and `DUPLICATE_JOB`.
- Marketplace simulation: fake workers and jobs exercise routing, audit logs, and reputation updates locally.

The intended protocol flow is:

```text
customer intent -> signed job envelope -> worker capability claim -> route decision
-> audit log -> worker receipt -> verification -> customer receipt
-> reputation update -> payout accounting
```

This is still local-only. There is no HTTP server, blockchain settlement, wallet integration, or external service dependency.

## Distributed Marketplace Simulation

QiCompute can now model unreliable distributed execution before real networking exists.

Lifecycle states are explicit:

```text
queued -> routed -> running -> completed
queued -> rejected
queued/routed/running/retrying -> expired
running -> failed -> retrying -> routed
```

Customer jobs can include `expires_at`. Stale queued, routed, running, or retrying jobs move to `expired` and are not routed. Retry policy tracks `retry_count`, `last_failure_code`, and `last_failure_reason`; timeout and overload failures are retryable, while duplicate jobs and invalid envelopes are not.

Worker registry records runtime load:

```text
current_jobs, max_concurrent_jobs, load_percent, last_heartbeat_at
```

The router skips overloaded workers and gives lower-load workers a better score. Marketplace simulation can model offline workers, latency, timeouts, slow workers, overloaded workers, and workers coming back online.

Adversarial worker modes are local and deterministic:

- `honest`
- `flaky`
- `slow`
- `malicious_receipt`
- `fake_capability`
- `duplicate_submitter`

Malformed receipts fail receipt-hash verification. Fake capability claims fail capability verification. Duplicate job replays do not create a second payout or reputation gain.

Reputation now supports decay and stronger failure penalties. Stale workers lose routing priority over time, offline workers route lower or not at all, repeated failures compound, and scores remain capped from 0 to 100.

The stress simulation creates 10 workers and 50 jobs with mixed models, privacy levels, latency targets, expirations, retries, and adversarial behavior:

```bash
python3 market.py --stress-sim
```

The summary includes completed, failed, expired, retried, rejected, average route score, average final price, best worker, worst worker, and whether the malicious worker was penalized.

Product framing remains simple: private distributed AI compute from idle GPU hardware. Qi is the settlement and incentive layer; customer-facing value is private, affordable, reliable inference.

Run continuously:

```bash
python3 worker.py
```

## Inference Jobs

Create a JSON file in `jobs/`:

```bash
mkdir -p jobs
cat > jobs/example.json <<'JSON'
{
  "id": "example-job-001",
  "prompt": "Summarize Qi compute pool accounting",
  "tokens": 512,
  "seconds": 2
}
JSON
python3 worker.py --once
```

The scheduler treats any `*.json` file in `jobs/` as available inference work. Completed jobs move to `jobs_done/`; failed jobs move to `jobs_failed/`.

## Launching Real Workloads

Both modes support a placeholder command in `config.yaml`:

```yaml
mining:
  command: ["bash", "./start-miner.sh"]

inference:
  command: ["python3", "./run_inference.py"]
```

An individual job may also specify a `command` and `timeout_seconds`.

## Accounting Model

Energy:

```text
joules = average_watts * duration_seconds
```

Output:

- Mining records accepted shares.
- Inference records input and output tokens from the job file, or `inference.default_tokens`.

Payout:

```text
settled_balance = sum(settled payout_events.qi_amount)
estimated_receipt_total = sum(receipts.estimated_qi_owed)
```

Receipts describe work. Payout events update balances. This keeps audit records separate from payable claims.

Inference payout:

```text
estimated_qi_owed =
  accepted_input_tokens  * estimated_qi_per_input_token
+ accepted_output_tokens * estimated_qi_per_output_token
```

Mining share accounting:

```text
accepted shares are recorded for PPLNS eligibility
accepted shares do not increase balances directly
```

Block reward payout:

```text
net_reward = block_reward - pool_fee
worker_reward = net_reward * worker_eligible_share_weight / total_eligible_share_weight
```

The block reward path uses a simple PPLNS-style window over unassigned accepted shares until cumulative share difficulty reaches `mining.pplns_window_weight`.

Receipts, payout events, and balances are local only. Future private Qi UTXO settlement can consume accepted payout events as the local source of payable claims.

## Verification

Inference payout is verification-aware:

```text
execute job
build receipt
hash receipt
verify receipt against job
store receipt
create payout event only if verification accepts and job_id has not already been paid
```

The local verifier checks:

- inference mode
- required job ID
- non-negative input/output token counts
- positive duration and energy
- explicit accepted status
- worker ID and receipt ID
- deterministic receipt hash

This is not a cryptographic proof system. It is a local validation layer preparing the prototype for future network verification.

## Verification Challenges

QiCompute can attach local proof-of-useful-work challenges to a configurable percentage of inference jobs. Challenge types are protocol-shaped placeholders:

- `deterministic_prompt`
- `known_output`
- `timing_challenge`
- `duplicate_execution`
- `partial_output_verification`

Challenges record expected hashes and token counts without adding networking or cryptographic proof systems. A worker receipt must include matching challenge response metadata. Failed or expired challenges are recorded in `challenge_results`, block payout eligibility for that job, and reduce worker reputation more heavily than ordinary failures.

## Verification Committees

Verification committees simulate decentralized useful-work review without networking. A committee selects online verifier workers from the local registry and excludes the worker that performed the job. Each verifier independently checks:

- receipt hash integrity
- challenge result status
- capability claim hash validity

Votes aggregate into `accepted`, `rejected`, or `disputed` using a configurable quorum threshold. Rejected or disputed committee results block payout eligibility and are persisted with vote metadata for auditability.

## Settlement Epochs

Settlement epochs batch verified payout events into deterministic local settlement windows. Payout events reference an `epoch_id`; finalizing an epoch summarizes:

- receipt count
- energy and token totals
- estimated and settled Qi totals
- verified and failed job counts
- worker totals
- challenge pass/fail counts
- committee accepted/rejected/disputed counts

Balances still derive only from settled payout events. Epochs are summary artifacts for future settlement batching, not a wallet or chain integration.

## Committee Consensus

Committee consensus gives QiCompute a local model for distributed trust. Accepted committees make work settlement-eligible. Rejected committees mark the job as failed verification. Disputed committees block payout until a future resolution path exists. If not enough verifiers are available to satisfy quorum, the result is treated as unresolved with `QUORUM_NOT_REACHED` metadata.

## Useful-Work Settlement

The local settlement path is now:

```text
energy -> inference work -> receipt -> challenge -> committee -> payout event -> epoch summary
```

QiCompute is evolving toward useful-work verification, batched settlement, distributed trust, and private distributed inference markets. Qi remains the settlement and incentive layer beneath the compute marketplace.

## Receipt Hashing

Each new receipt includes a deterministic SHA-256 hash. The hash covers the stable receipt payload:

```text
receipt_id, worker_id, mode, timestamps, duration, watts, joules,
output type/amount, estimated value, and metadata
```

`receipt_hash` itself is excluded from the hash payload.

## Idempotency

Accepted inference jobs are tracked by `job_id`. If the same accepted job appears again, the worker stores another receipt for auditability but does not create a second payout event.

## SQLite Tables

- `telemetry`: timestamped GPU samples.
- `receipts`: one row per mining or inference cycle.
- `payout_events`: payable events that update worker balances.
- `inference_jobs`: accepted inference job IDs that have already been paid.
- `worker_registry`: local worker capability, heartbeat, and reputation records.
- `customer_jobs`: local customer-facing job queue with prompt hashes, not raw prompts.
- `routing_audit_logs`: local route decision audit records.
- `mining_shares`: accepted/rejected share records for pool reward allocation.
- `mining_rounds`: block reward distribution records.
- `balances`: local estimated Qi owed by worker ID.
