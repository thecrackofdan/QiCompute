# QiCompute Hardware Testing Guide

This guide covers the exact test procedures, required data, and expected outputs for running the QiCompute pipeline against real GPU hardware.

QiCompute's inference layer is entirely GPU-based. Under Quai's TWP (Tensor Work Proof) native merge-mining algorithm, the GPU running InferenceGemm **is** the miner — Tensor Work Receipts are submitted as Quai workshares and earn Qi rewards directly. No ASIC hardware is required.

## The Hardware Stack & Roles

| Hardware | Algorithm | Role in QiCompute |
|---|---|---|
| **RTX 3090** | KawPoW + TWP | Reference rig. Anchors Claim 3 inference baseline and Claim 6 dual-revenue model. |
| **2x RTX 3080** | KawPoW + TWP | Secondary rigs. Validate that joules/token is stable across GPU tiers. |

---

## Phase 1: Calibrate the KawPoW Reference Rig

First, measure the actual KawPoW hashrate and wattage of the 3090 to replace the spec-sheet defaults in `research.yaml`.

1. Edit `research.yaml` and set `benchmark.miner_command` to your KawPoW miner invocation (e.g., T-Rex, lolMiner, or TeamRedMiner pointed at your local node stratum).
2. Run the calibration:
   ```bash
   python3 benchmark.py --calibrate-rig --algo kawpow --minutes 5
   ```

**Expected Output:**
```
calibrate-rig (kawpow): running [...] for 5.0 minutes...

Measured kawpow reference rig - paste into research.yaml under 'reference_gpu':
reference_gpu:
  name: "RTX 3090"
  hashrate_hps: 47200000
  watts: 295
```

*Action:* Paste this block into the `reference_gpu:` section of `research.yaml`, replacing the defaults.

---

## Phase 2: Calibrate Inference (GPU)

Claim 3 asserts that inference can be priced consistently in joules. We need to measure the actual joules per token on your GPUs.

There are two supported inference backends:

| Backend | Setup | Use Case |
|---|---|---|
| **Ollama** (`backend: ollama`) | `ollama pull qwen2.5:3b` | Fast setup, unverified inference |
| **InferenceGemm** (`backend: igemm`) | See below | Production — emits Tensor Work Receipts (TWP) |

For production Quai inference, the InferenceGemm backend is required because it ties joules/token measurements to cryptographically verifiable Tensor Work Receipts. Dominant Strategies has published the reference checkpoint at [huggingface.co/dominant-strategies/quai-igemm-qwen2.5-3b-w8a8-research](https://huggingface.co/dominant-strategies/quai-igemm-qwen2.5-3b-w8a8-research), with a measured TWP overhead of only **2.98%** — meaning receipt-mode inference is essentially the same cost as unverified inference.

### Option A: Ollama Backend (Quick Start)

1. Ensure Ollama is running and the `qwen2.5:3b` model is pulled:
   ```bash
   ollama pull qwen2.5:3b
   ```
2. Run the benchmark and store the result:
   ```bash
   python3 benchmark.py --minutes 5 --store --contributor "your_handle"
   ```

**Expected Output:**
The script will drive the model with prompts for 5 minutes, measuring tokens/sec and reading GPU wattage via `nvidia-smi`. It will print the final `joules_per_token` (typically 3–5 J/token for a 3090) and append the record to `measurements.db`.

### Option B: InferenceGemm Backend (Production TWP)

1. Serve the InferenceGemm checkpoint via vLLM:
   ```bash
   pip install vllm
   vllm serve "dominant-strategies/quai-igemm-qwen2.5-3b-w8a8-research" --port 8000
   ```
2. Update `research.yaml` to switch to the igemm backend:
   ```yaml
   benchmark:
     backend: "igemm"
   ```
3. Run the benchmark:
   ```bash
   python3 benchmark.py --minutes 5 --store --contributor "your_handle"
   ```

**Expected Output:**
In addition to `joules_per_token`, the script will print `receipts_accepted` (the number of Tensor Work Receipts emitted during the run) and compare the measured overhead against the pre-registered 10% ceiling (P3b). The Dominant Strategies reference result is **2.98% overhead** with 1 accepted receipt on the 3B model.

### Option C: TWP Calibration (Receipts/sec)

To measure the TWP-specific energy factor for the multi-algorithm model:

```bash
python3 benchmark.py --calibrate-rig --algo twp --minutes 5
```

**Expected Output:**
```
calibrate-rig (twp): measuring InferenceGemm receipts/sec for 5.0 minutes...

calibrate-rig (twp) results:
  receipts/sec : 62.6
  watts        : 290.0 W
  J/receipt    : 4.6326
  energy_factor vs KawPoW ref: 0.6940

Paste into research.yaml soap section:
  reference_twp:
    name: "dominant-strategies/quai-igemm-qwen2.5-3b-w8a8-research"
    hashrate_hps: 62   # receipts/sec
    watts: 290.0
  algo_energy_factors:
    twp: 0.694000   # measured J/receipt / J/KawPoW-hash
```

*Action:* Paste this into the `soap:` section of `research.yaml`.

### Secondary Rigs (RTX 3080s)

Repeat the same benchmark command on the machines hosting the 3080s. This proves that joules/token is relatively stable across GPU tiers within the same generation.

---

## Phase 3: Building the Local Data Cache

Because you are solo mining, your local Quai node has the freshest, most accurate block data, including the workshare lock fields needed for Claims 5 and 7.

1. Edit `research.yaml` and set `difficulty.rpc_url` to your local node's RPC endpoint:
   ```yaml
   difficulty:
     rpc_url: "http://127.0.0.1:8545"
   ```
2. Run the data fetcher:
   ```bash
   python3 fetch_data.py
   ```

**Expected Output:**
The script will scan the blockchain and build local JSON/CSV caches in the `data/` directory for:

| Dataset | Claim |
|---|---|
| `difficulty` | Claim 1 (energy peg) |
| `token_choice_qi_fraction` | Claim 5 (controller directionality) |
| `exchange_rate_qi_per_quai` | Claim 5 (market vs on-chain rate) |
| `workshare_difficulty_kawpow_ws` | Claim 7 (TWP adoption) |
| `workshare_difficulty_twp_ws` | Claim 7 (TWP adoption) |

*Note:* The RPC scan can take a while on the first run. Subsequent runs will only fetch new blocks incrementally.

---

## Phase 4: Running the Dual-Revenue Daemon

Claim 6 models the economics of running inference while simultaneously earning Qi workshare rewards via TWP. The `crossover-daemon` executes this logic in real time.

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
The daemon evaluates the profitability of mining vs. inference every 60 seconds and logs decisions to `crossover.db`. Let this run for at least 24 hours, then generate the report:

```bash
python3 report.py
```

This produces `report.md` and a revenue comparison chart showing how the dual-revenue model performed in reality compared to mining alone.

---

## Phase 5: The Live Dashboard

Once all data is flowing, monitor the entire project state from a single terminal window:

```bash
python3 qi_dashboard.py --watch 60
```

**Expected Output:**
A live-updating CLI dashboard showing:
- The current Qi Index (from your 3090's joules/token measurement).
- The Claim 1 peg verdict.
- The miner token choice ratio (Claim 5).
- The TWP workshare adoption rate and energy fraction (Claim 7).
- The dual-revenue economics (Claim 6).
