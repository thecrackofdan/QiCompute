# Qi Compute Pool Worker Prototype

Local Python prototype for a unified Qi compute/mining pool worker. It runs on a GPU rig and chooses inference work when a local job is available, otherwise it falls back to mining mode.

This MVP has no smart contracts and no real payout rail. It records local receipts, telemetry, estimated energy usage, output, and estimated Qi owed in SQLite.

## Components

- `worker.py`: CLI entrypoint and config loading.
- `scheduler.py`: mode selection, placeholder launchers, accounting.
- `telemetry.py`: GPU telemetry via `nvidia-smi`, with fallback watts when unavailable.
- `receipts.py`: local job receipt format.
- `verifier.py`: local inference receipt validation.
- `registry.py`: local worker registry helpers.
- `router.py`: local inference job routing.
- `reputation.py`: worker reputation updates.
- `pricing.py`: local marketplace pricing estimates.
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

Routing considers online status, model support, reputation, region preference, VRAM, latency, energy efficiency, and failure rate. This is local route planning only; no network calls are made.

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
- `mining_shares`: accepted/rejected share records for pool reward allocation.
- `mining_rounds`: block reward distribution records.
- `balances`: local estimated Qi owed by worker ID.
