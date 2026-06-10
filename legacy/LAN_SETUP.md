# LAN Setup

QiCompute cluster mode is a trusted LAN controller prototype. It is intended for home GPU rigs on a private network, not public internet exposure.

## Controller Setup

On the controller machine:

```bash
git clone https://github.com/thecrackofdan/QiCompute.git
cd QiCompute
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 controller.py --host 192.168.x.x --port 8080
```

## Worker Enrollment

Create and activate a worker:

```bash
python3 enroll.py --create-worker worker-3080-a
python3 enroll.py --activate-worker worker-3080-a --print-config
```

The shared secret is printed once. Store it only on the worker machine. QiCompute stores only a hash in the controller DB.

## Worker Config

Use the config snippet from activation, or write it directly:

```bash
python3 enroll.py --activate-worker worker-3080-a --write-config worker-3080-a.yaml
```

Set `cluster.controller_url` to the controller LAN IP.

## Ollama

Install Ollama separately on each worker and pull a local model:

```bash
ollama pull llama3.1:8b
```

## Start Workers

On each worker:

```bash
python3 daemon.py --config worker-3080-a.yaml --cluster-worker --runtime ollama
```

## Verify Health

On the controller:

```bash
python3 cluster_health.py
python3 cluster_ctl.py workers
python3 cluster_ctl.py jobs
python3 cluster_ctl.py epochs
python3 accounting_checks.py
```

`accounting_checks.py` verifies local escrow, treasury, worker payable, refund, and duplicate-payment consistency. It does not perform blockchain or wallet settlement.

## Run Local Validation

Single-machine deterministic smoke test:

```bash
python3 lan_smoke_test.py
```

## Privacy Defaults

Strict mode is enabled by default:

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

Do not store raw prompts or raw model outputs. Cluster receipts carry hashes, byte counts, token counts, timing, energy, and verification metadata. The local runtime may receive a prompt transiently for execution, but logs, receipts, audits, snapshots, and summaries should not retain it.

The encrypted job payload support is a local prototype boundary, not audited production cryptography. Keep cluster mode on a trusted LAN.
