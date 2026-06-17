# QiCompute Hardware Testing Guide

This guide covers the exact test procedures, required data, and expected outputs for running the QiCompute pipeline against a real, multi-algorithm hardware stack.

If you are running a solo Quai node and possess a mix of GPU and ASIC hardware, you can generate the real-world data required to move the project's claims from synthetic models to empirical truth.

## The Hardware Stack & Roles

This guide is tailored for the following setup:

| Hardware | Algorithm | Role in QiCompute |
|---|---|---|
| **Avalon Q** | SHA-256 | SOAP workshare baseline. Feeds Claim 7 (ASIC adoption) and calibrates Claim 6 (dual-revenue). |
| **2x BitAxe** | SHA-256 | Lightweight SOAP nodes. Used to measure per-unit workshare frequency. |
| **2x Home DG1** | Scrypt | SOAP Scrypt workshare baseline. Feeds the multi-algo energy model (Claim 1). |
| **2x RTX 3080** | KawPoW | Primary mining & inference. Feeds Claim 1 (difficulty) and Claim 3 (joules/token). |
| **RTX 3090** | KawPoW | The reference rig. Anchors the Claim 3 inference baseline and Claim 6 crossover daemon. |

---

## Phase 1: Calibrating the Energy Model (ASICs)

Currently, `research.yaml` uses spec-sheet estimates for SHA-256 and Scrypt ASIC energy efficiency. Your ASICs will replace these estimates with real, measured data.

### 1. SHA-256 Calibration (Avalon Q)

You need to measure the actual hashrate and wattage of the Avalon Q while it is hashing.

1. Ensure the Avalon Q is running and accessible.
2. Edit `research.yaml` to include your miner command and hashrate regex in the `sha256_miner_command` and `sha256_hashrate_regex` fields.
3. Run the calibration script:
   ```bash
   python3 benchmark.py --calibrate-rig --algo sha256 --minutes 5
   ```

**Expected Output:**
The script will output a YAML block looking something like this:
```yaml
soap.reference_sha256:
  hashrate_hps: 110000000000000  # 110 TH/s
  watts: 3300
```
*Action:* Paste this block into the `soap:` section of `research.yaml`, replacing the stub. The script will also calculate and print the `algo_energy_factors.sha256` value — update that field in `research.yaml` as well.

### 2. Scrypt Calibration (Home DG1)

Repeat the process for the Scrypt ASIC.

1. Edit `research.yaml` to include your Scrypt miner command and regex.
2. Run the calibration script:
   ```bash
   python3 benchmark.py --calibrate-rig --algo scrypt --minutes 5
   ```

**Expected Output:**
A YAML block for `soap.reference_scrypt`.
*Action:* Paste this into `research.yaml` and update `algo_energy_factors.scrypt`.

---

## Phase 2: Calibrating Inference (GPUs)

Claim 3 asserts that inference can be priced consistently in joules. We need to measure the actual joules per token on your GPUs.

### 1. Reference Rig (RTX 3090)

This establishes the baseline cost of inference.

1. Ensure Ollama is running and the `llama3.1:8b` model is pulled (`ollama run llama3.1:8b`).
2. Run the benchmark and store the result:
   ```bash
   python3 benchmark.py --minutes 5 --store --contributor "your_handle"
   ```

**Expected Output:**
The script will hammer Ollama with prompts for 5 minutes, measuring tokens/sec and reading GPU wattage via `nvidia-smi`. It will print the final `joules_per_token` (typically ~3.0 - 4.0 for a 3090) and append the record to `measurements.db`.

### 2. Secondary Rigs (RTX 3080s)

Repeat the exact same command on the machines hosting the 3080s. This proves that the joules/token metric is relatively stable across different hardware tiers within the same generation.

---

## Phase 3: Building the Local Data Cache

Because you are solo mining, your local Quai node has the freshest, most accurate block data, including the workshare lock fields and SOAP data needed for Claims 5 and 7.

1. Edit `research.yaml` and set `rpc_url` to your local node's RPC endpoint (e.g., `http://127.0.0.1:8545`).
2. Run the data fetcher:
   ```bash
   python3 fetch_data.py
   ```

**Expected Output:**
The script will scan the blockchain and build local JSON/CSV caches in the `data/` directory for:
- `difficulty`
- `token_choice_qi_fraction` (Claim 5)
- `exchange_rate_qi_per_quai` (Claim 5)
- `workshare_difficulty_kawpow_ws` (Claim 7)
- `workshare_difficulty_soap_ws` (Claim 7)

*Note:* The RPC scan can take a while on the first run. Subsequent runs will only fetch new blocks.

---

## Phase 4: Running the Dual-Revenue Daemon

Claim 6 models the economics of running inference while simultaneously mining Quai workshares. The `crossover-daemon` actually executes this logic.

1. Navigate to the daemon directory:
   ```bash
   cd tools/crossover-daemon
   ```
2. Edit `config.yaml`:
   - Set `usd_per_kwh` to your actual power rate.
   - Configure `miner_command` with your KawPoW miner execution string.
   - Configure `difficulty_feed.url` to your local node.
3. Run the daemon on the RTX 3090 machine:
   ```bash
   python3 daemon.py
   ```

**Expected Output:**
The daemon will evaluate the profitability of mining vs. inference every 60 seconds. It will log its decisions to `crossover.db`. Let this run for at least 24 hours.

After 24 hours, run:
```bash
python3 report.py
```
This will generate `report.md` and a revenue comparison chart showing how the dual-revenue model performed in reality compared to mining alone.

---

## Phase 5: The Live Dashboard

Once all the data is flowing, you can monitor the entire project state from a single terminal window.

Run:
```bash
python3 qi_dashboard.py --watch 60
```

**Expected Output:**
A live-updating CLI dashboard showing:
- The current Qi Index (calculated from your 3090's joules/token measurement).
- The Claim 1 peg verdict.
- The miner token choice ratio (Claim 5).
- The SOAP adoption rate and workshare energy fraction (Claim 7).
- The dual-revenue economics (Claim 6).
