# Qi Compute Pool Worker Prototype

Local Python prototype for a unified Qi compute/mining pool worker. It runs on a GPU rig and chooses inference work when a local job is available, otherwise it falls back to mining mode.

This MVP has no smart contracts and no real payout rail. It records local receipts, telemetry, estimated energy usage, output, and estimated Qi owed in SQLite.

## Components

- `worker.py`: CLI entrypoint and config loading.
- `scheduler.py`: mode selection, placeholder launchers, accounting.
- `daemon.py`: local worker execution daemon for assigned jobs.
- `runtime.py`: runtime result structure and local runtime implementations.
- `runners.py`: lightweight model runner adapters.
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
- `demo.py`: end-to-end local inference settlement demo.
- `controller.py`: local LAN controller HTTP skeleton.
- `cluster_demo.py`: deterministic local cluster demo.
- `transport.py`: signed JSON transport helpers.
- `enroll.py`: LAN worker enrollment CLI.
- `cluster_ctl.py`: operator inspection CLI.
- `lan_smoke_test.py`: one-command local LAN validation.
- `doctor.py`: local environment validation.
- `benchmarks.py`: lightweight runtime benchmark stubs.
- `logging_config.py`: privacy-preserving logging helpers.
- `db.py`: SQLite schema and persistence.
- `config.yaml`: local worker configuration.
- `config.demo.yaml`: local Ollama demo configuration.
- `ARCHITECTURE.md`: architecture overview.
- `ROADMAP.md`: prototype roadmap.
- `CONTRIBUTING.md`: contribution and privacy rules.
- `LAN_SETUP.md`: LAN controller/worker deployment guide.

## Requirements

- Ubuntu with Python 3.10+.
- NVIDIA drivers with `nvidia-smi` for real GPU telemetry.
- Optional: `PyYAML`. The worker includes a small fallback parser for the provided `config.yaml`.

## Quickstart

Fresh clone setup:

```bash
git clone https://github.com/thecrackofdan/QiCompute.git
cd QiCompute
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m unittest -v
python3 demo.py --mode honest
```

The test suite does not require Ollama. The honest demo uses local Ollama by default; if Ollama is not running, use `python3 demo.py --mode flaky` to see the failure/reputation path or run daemon tests with the simulated runtime.

Useful local commands:

```bash
make test
make demo
make stress
make lint
python3 doctor.py
python3 benchmarks.py
```

## Worker Quick Start

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

Run the local worker daemon once:

```bash
python3 daemon.py --once --runtime simulated
```

Run continuously:

```bash
python3 daemon.py --loop --runtime simulated
```

## Running Local Ollama

Ollama is installed separately from QiCompute. The demo defaults to the local Ollama generate endpoint:

```text
http://127.0.0.1:11434/api/generate
```

Recommended starter model:

```bash
ollama pull llama3.1:8b
```

`config.demo.yaml` uses:

```yaml
runtime:
  type: "ollama"
  ollama_url: "http://127.0.0.1:11434/api/generate"
  ollama_model: "llama3.1:8b"
```

Raw prompts are sent only to the local Ollama process for inference. QiCompute does not store raw prompts or raw model outputs; it stores hashes, counts, timing, energy, and verification metadata.

## Local LAN Cluster Prototype

QiCompute includes a minimal controller/worker cluster skeleton for trusted LAN experimentation. It is disabled by default:

```yaml
cluster:
  enabled: false
  node_role: "controller"
  controller_url: "http://127.0.0.1:8080"
  worker_bind_host: "127.0.0.1"
  worker_bind_port: 8081
  shared_secret: "dev-local-secret"
  allow_dev_shared_secret: false
  heartbeat_interval_seconds: 10
  request_timeout_seconds: 5
```

Current decentralization status: QiCompute is privacy-first and decentralization-ready, but cluster mode is still a trusted LAN controller prototype. The controller is trusted to hold the job queue, registry, local verification decisions, audit logs, and settlement epoch summaries.

The controller accepts signed worker heartbeats, capability claims, receipt submissions, and challenge results. It assigns queued jobs to eligible workers, runs local receipt verification, attaches accepted payouts to active settlement epochs, and writes `cluster_events` audit logs.

The worker sends heartbeat/capability messages, polls for the next job, executes locally through the selected runtime, and submits a receipt with hashes, token counts, timing, energy, and verification metadata. Raw prompts and raw model outputs are not sent back by default.

Cluster hardening features:

- Persistent replay protection stores accepted nonces in SQLite, so replayed messages fail across controller restarts.
- Worker enrollment records can be `pending`, `active`, or `revoked`.
- Active workers authenticate with per-worker secrets; raw secrets are not stored, only hashes.
- The development shared-secret fallback is disabled in `config.yaml` and enabled only in demo config for local demos.
- Job leases prevent disappeared workers from locking jobs forever. Expired leases can be requeued and reassigned.
- Controller snapshots export registry, jobs, leases, events, audit logs, and epoch state without raw prompts or raw outputs.

Run a controller:

```bash
python3 controller.py --host 127.0.0.1 --port 8080
```

Run a worker in cluster mode:

```bash
python3 daemon.py --cluster-worker
```

Run the deterministic single-process cluster demo:

```bash
python3 cluster_demo.py
```

Run a multi-worker local demo:

```bash
python3 cluster_demo.py --workers 3 --jobs 10
python3 cluster_demo.py --workers 5 --jobs 50 --simulate-worker-failure
```

Inspect cluster health:

```bash
python3 cluster_health.py
```

Enroll and activate a real LAN worker:

```bash
python3 enroll.py --create-worker worker-3080-a
python3 enroll.py --activate-worker worker-3080-a --print-config
```

Inspect controller state:

```bash
python3 cluster_ctl.py workers
python3 cluster_ctl.py jobs
python3 cluster_ctl.py epochs
python3 cluster_ctl.py events
```

Run the local LAN smoke test:

```bash
python3 lan_smoke_test.py
```

Cluster transport uses standard-library HTTP plus shared-secret HMAC request signing with timestamp, nonce, and body hash. This is for local LAN development only. There is no public networking, blockchain integration, wallet integration, or cloud dependency.

## Privacy Model

QiCompute defaults to strict privacy mode:

```yaml
privacy:
  mode: "strict"
  store_raw_prompts: false
  store_raw_outputs: false
  encrypt_job_payloads: true
  controller_blind_prompts: true
  zero_retention_runtime: true
  allow_debug_prompt_logging: false
```

Strict mode keeps raw prompts and raw model outputs out of SQLite, receipts, routing audit logs, cluster events, controller snapshots, summaries, and normal logs. Runtimes store hashes, byte counts, token counts, timing, energy estimates, and failure codes.

`privacy.py` adds a local prototype private payload envelope with `encrypted_payload`, `payload_nonce`, `payload_hash`, and `privacy_mode`. This is standard-library-only placeholder encryption for LAN architecture testing. It is not audited cryptography and is not production end-to-end encryption.

With zero-retention runtime enabled, subprocess and Ollama execution avoid persisting raw stdout, stderr, prompts, or model responses. The local runtime may receive the prompt transiently for execution, but receipts carry output hashes and counts only.

With controller-blind prompt handling enabled, the controller routes by model, token estimates, price limits, privacy level, hashes, and worker capability. It does not need raw prompts. Worker job payloads carry the private payload envelope and hashes, not raw prompt text or transient keys.

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

## Local Runtime Boundary

The daemon separates marketplace control-plane state from local execution. It polls SQLite for jobs assigned to the local worker, marks them running, executes through a selected runtime, creates a receipt, verifies it, updates reputation, and moves the job to completed or failed.

Runtime types are local-only:

- `simulated`
- `subprocess`
- `ollama`
- `ollama_placeholder`
- `llama_cpp_placeholder`

The subprocess runtime requires commands as argument lists and runs with `shell=False`. It captures stdout/stderr, enforces timeouts, hashes stdout as `output_hash`, and maps timeout/nonzero exits to structured failure codes. Raw prompts and raw model outputs are not stored by default.

Runtime config:

```yaml
runtime:
  type: "simulated"
  timeout_seconds: 300
  max_concurrent_jobs: 1
  command: []
  redact_outputs: true
  store_output_hash_only: true
  ollama_url: "http://127.0.0.1:11434/api/generate"
  ollama_model: "llama3.1:8b"
```

The Ollama runtime calls a local Ollama endpoint with the Python standard library only. It sends the prompt to local Ollama for execution, hashes the returned text, estimates output tokens when needed, and stores only hashes/counts/timing/runtime metadata in receipts. It does not persist raw prompts or raw model output.

The Ollama placeholder and llama.cpp adapter remain placeholders shaped for future local integrations. They do not import SDKs or start servers.

## Local End-to-End Demo

`demo.py` runs a complete local useful-compute settlement path:

```text
submit job -> route job -> daemon executes Ollama inference -> runtime result
-> worker receipt -> challenge verification -> committee verification
-> payout eligibility -> epoch finalization -> settlement summary
```

Run the honest local demo:

```bash
python3 demo.py
```

The demo uses `config.demo.yaml`, defaults to local Ollama at `http://127.0.0.1:11434/api/generate`, and requests model `llama3.1:8b`. The prompt is sent only to local Ollama for execution. Raw prompts and raw model outputs are not stored; QiCompute stores prompt hashes, output hashes, token counts, timing, energy, verification metadata, and settlement summaries.

Demo modes:

```bash
python3 demo.py --mode honest
python3 demo.py --mode flaky
python3 demo.py --mode malicious
```

- `honest`: executes the job, passes challenge verification, reaches committee acceptance, creates a payout event, and finalizes the epoch with settled Qi.
- `flaky`: simulates local runtime unavailability, marks the job failed, and reduces worker reputation.
- `malicious`: tampers challenge response metadata, fails useful-work verification, blocks payout, and records the rejection path.

The printed settlement summary includes epoch totals, worker reputation, job outcome, committee outcome, challenge pass rate, committee acceptance rate, settled Qi, rejected Qi, latency, energy per token, and runtime type distribution.

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
