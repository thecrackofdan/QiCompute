# Changelog

All notable changes to QiCompute are documented here. This project follows the spirit of Keep a Changelog and uses semantic versioning for experimental MVP releases.

## [Unreleased]

### Added (K-Quai Controller ## [Unreleased] Energy Model Calibration)
- **Dynamic `k_Qi` block reward formula**: Replaced the hardcoded `block_reward_qi: 3` with the protocol-authoritative `k_Qi` formula (`reward = (1 / 8e9) * difficulty`). This corrects a ~57x underestimation of the block reward pool and fixes the absolute scale of all level claims (`joules_per_qi`, Qi index). Claim 1 log-returns are mathematically invariant to this constant, but level claims are now accurate.
- **K-Quai controller mechanics updated**: Corrected the documentation and `claim5` docstrings to reflect that the K-Quai controller uses a proportional update (`alpha = 0.001`), not a logistic regression, and operates on `minerDifficulty` (a 4,000-block EMA), not raw block difficulty.
- **`fetch_data.py` tracking**: Added parsing for `minerDifficulty` from block headers in preparation for deeper controller modeling.

## [0.2.0] - 2026-06-17

### Added (TWP as first-class merge-mining algorithm — protocol confirmation)

- **TWP inference confirmed as native Quai merge-mining algorithm**: the Quai team has
  confirmed (AMA, Jun 2026) that Tensor Work Proof (TWP) inference will be added as a
  first-class merge-mining algorithm alongside SHA-256 (BCH/BTC), Scrypt (LTC/DOGE), and
  Ravencoin KawPoW. This means GPU inference nodes running InferenceGemm will submit TWP
  receipts as native Quai workshares and earn Qi rewards — no co-located ASIC required.
- **`benchmark.py --algo twp`** added: calibrates a GPU inference rig via the igemm backend,
  measures receipts/sec and watts, computes the energy_factor vs KawPoW reference, and
  prints the `research.yaml soap.reference_twp` block to paste in.
- **`fetch_data.py` `twp_ws` bucket** added to `fetch_workshare_difficulty()`: tracks
  `workshare_difficulty_twp_ws` as a separate daily series using the `twpReceipt`/
  `tensorReceipt` field heuristic. Ready to populate once TWP launches on mainnet.
- **`research.yaml soap.algo_energy_factors`** extended with `rvn: 1.0` (Ravencoin KawPoW,
  same algorithm as Quai) and `twp: 0.001` (placeholder; replace with
  `benchmark.py --calibrate-rig --algo twp` output).
- **`research.yaml soap`** extended with `reference_rvn` and `reference_twp` stub blocks
  and TWP miner command/regex fields for future calibration.
- **`_ALGO_CONFIG` in `benchmark.py`** extended with `rvn` and `twp` entries.
- **`claim6_workshare_inference.py`** reframed: docstring and `render_markdown()` updated
  to reflect that the GPU IS the miner under TWP — the TWP receipt is the proof-of-work,
  the Qi reward is the block subsidy, the inference fee is the transaction fee.
- **`claim7_soap_adoption.py`** updated: docstring, `render_markdown()` intro, and
  interpretation notes updated to track SOAP + TWP adoption together as the energy anchor
  broadening signal. P7 in `PREDICTIONS.md` retitled to "SOAP + TWP adoption rate".
- **Objection (n)** added to `OBJECTIONS.md`: "TWP as native algorithm obsoletes the
  workaround framing" — with a full treatment of why the model strengthens rather than
  breaks when TWP launches.

### Added (InferenceGemm backend & TWP overhead — Dominant Strategies alignment)

- **InferenceGemm backend support in `benchmark.py`**: a new `igemm` backend drives the
  Dominant Strategies InferenceGemm harness (vLLM-compatible endpoint) instead of Ollama.
  The backend emits Tensor Work Receipts per inference run and reports `receipts_accepted`
  alongside the standard `joules_per_token` output. Controlled by `benchmark.backend` in
  `research.yaml` (`"ollama"` default, `"igemm"` for production).
- **Reference model updated to Qwen2.5-3B W8A8**: `research.yaml` `benchmark.model` changed
  from `llama3.1:8b` to `qwen2.5:3b` (Ollama) / `dominant-strategies/quai-igemm-qwen2.5-3b-w8a8-research`
  (igemm), aligning with the Dominant Strategies reference implementation.
- **TWP overhead threshold (P3b)** added to `research.yaml` (`twp_overhead_threshold: 0.10`):
  pre-registered ceiling of 10% overhead for receipt-mode vs baseline throughput. Dominant
  Strategies measured 2.98% on the 3B model (64.49 → 62.57 tok/s).
- **`igemm_url` and `igemm_model`** fields added to `research.yaml benchmark:` section for
  configuring the InferenceGemm server endpoint and HuggingFace checkpoint path.
- **P3b sub-prediction** added to `PREDICTIONS.md`: receipt-mode overhead ≤ 10% of baseline
  tok/s, with the Dominant Strategies 2.98% reference result documented.
- **Objection (m)** added to `OBJECTIONS.md`: "InferenceGemm's TWP adds non-trivial overhead"
  — with a full treatment of why the overhead is small (Merkle roots over in-memory tensors)
  and the pre-registered test that would falsify this response.
- **`HARDWARE_SETUP.md` Phase 2** updated with a two-path setup guide: Ollama (quick start)
  and InferenceGemm (production), including `vllm serve` command and expected output format.

### Added (SOAP multi-algorithm energy model)

- **Multi-algorithm energy model in claim 1** (`claim1_peg.py`): the cost model now accounts
  for SHA-256 (BCH/BTC) and Scrypt (LTC/DOGE) ASIC workshares submitted via Project SOAP
  (launched Dec 2025). An energy-normalised effective difficulty is computed:
  `total_effective_difficulty = kawpow_difficulty + Σ(ws_difficulty[algo] × energy_factor[algo])`.
  When workshare data is available, the output notes which algorithms contributed and reports
  the workshare energy fraction. When unavailable, the single-algorithm KawPoW baseline is
  used and the output notes the undercount.
- `fetch_data.py` gains `fetch_workshare_difficulty()`: an incremental RPC scan that samples
  the `workshares` field of each block header, splitting into `workshare_difficulty_kawpow_ws`
  (KawPoW sub-threshold workshares, identified by presence of `mixHash`) and
  `workshare_difficulty_soap_ws` (SOAP/ASIC workshares). Both series extend incrementally
  on repeated runs. The algorithm split is heuristic pending an RPC upgrade that exposes
  an explicit algorithm field; this limitation is documented in the function docstring.
- `sample_data.py` gains deterministic synthetic fixtures for both workshare series:
  `workshare_difficulty_kawpow_ws` (proportional to block difficulty with sinusoidal noise)
  and `workshare_difficulty_soap_ws` (zero before day 45, then a logistic adoption curve
  reaching Bitcoin-scale SHA-256 difficulty), so the multi-algo pipeline can be exercised
  offline.
- `research.yaml` gains a `soap:` section with:
  - `algo_energy_factors`: default J/hash normalisation factors for kawpow, sha256, scrypt,
    and soap_ws (derived from published ASIC specs; replaceable with measured values).
  - `reference_sha256` and `reference_scrypt`: stub blocks for ASIC rig calibration output.
  - `sha256_miner_command`, `scrypt_miner_command`, and associated regex/multiplier fields
    for `benchmark.py --calibrate-rig --algo sha256/scrypt`.
- `benchmark.py` gains `--algo` argument for `--calibrate-rig`: supports `kawpow` (default,
  existing behavior), `sha256` (SHA-256 ASIC), and `scrypt` (Scrypt ASIC). For ASIC rigs,
  prints the `soap.reference_sha256` / `soap.reference_scrypt` block and computes the
  `energy_factor` relative to the KawPoW reference rig automatically.
- `PREDICTIONS.md` P1 gains a **Multi-algorithm note (SOAP)** explaining that the
  returns-based verdict is invariant to the extension (workshare difficulty also cancels
  in log-returns) while level claims are improved by the more complete energy accounting.
- `OBJECTIONS.md` gains objection (j): "SOAP workshares make the energy model incomplete"
  — with a full treatment of the heuristic algorithm split, the level-vs-returns invariance,
  and why merge-mining is a strength of the thesis (broader, more diverse energy anchor).

### Added (claim 5 — miner token choice & directionality)

- **Claim 5** (`claim5_token_choice.py`): empirically tests the K-Quai controller's
  directionality claim — that the on-chain QUAI↔Qi exchange rate responds to miner
  token preference in the direction the monetary theory predicts.
  - P5a: `corr(qi_fraction[t-1], Δexchange_rate[t]) < 0` (controller raises the Qi-per-QUAI
    rate when miners prefer QUAI).
  - P5b: lagged cross-correlation test — miner preference should *lead* rate adjustments
    by ≥ 1 day (negative peak at lag k in {1..14}).
  - P5c: market-implied rate (QUAI_USD / QI_USD) should track the on-chain protocol rate
    within ±20%; reported as `insufficient_data` when QI market price is unavailable.
- `fetch_data.py` gains two new incremental RPC scan series:
  - `token_choice_qi_fraction`: daily fraction of blocks where `woHeader.lock == 0x1`
    (miner elected Qi), sampled from the Quai RPC at the configured `rpc_block_step`.
  - `exchange_rate_qi_per_quai`: daily on-chain K-Quai controller rate from
    `header.exchangeRate` (hex big.Int / 1e18 = Qi per QUAI).
  Both series extend incrementally on repeated runs (same pattern as difficulty rpc_scan).
- `sample_data.py` gains deterministic synthetic fixtures for both new series: a
  low-qi_fraction oscillation and a lagged exchange rate response, so the claim-5
  pipeline can be exercised offline.
- `research.yaml` gains a `claim5:` section with pre-registered thresholds for
  min_samples, min_leading_corr, max_market_onchain_deviation, and
  max_consecutive_deviation_days.
- `PREDICTIONS.md` gains P5 with numeric failure conditions for all three sub-claims.
- `OBJECTIONS.md` gains objection (i): "If miners choose QUAI over Qi, the energy peg
  breaks" — with a full treatment explaining why the directionality mechanism preserves
  the anchor regardless of miner preference.

### Changed (rigor hardening)

- Claim 1 gains ETH as a second crypto-beta null (fetched/cached/synthesized like BTC); the thesis must beat every null, and the verdict names the strongest one.
- Honesty fix: the returns-based claim-1 verdict is scale-invariant to the cost model's constants ($/kWh, reference hashrate/watts cancel in log-returns), so the previously prescribed $/kWh "verdict robustness rerun" was vacuous. The docs now state the invariance (a stronger answer to the regional-electricity objection), and a level sensitivity is reported instead: median price-to-modeled-cost ratio at $0.04/$0.12/$0.20 per kWh, which any level claim must quote as a range.
- Pre-registration is now enforced in code: until `verdict.thresholds_frozen` is set (after PREDICTIONS.md candidates are reviewed and frozen, before seeing real output), every claim-1 result is stamped "THRESHOLDS DRAFT - not citable" in the report, stats JSON, and reproduce summary.

### Changed (Quai/Qi focus)

- `benchmark.py` is now pure Quai/Qi measurement: claim 3 joules/token (unchanged boundary, storage, and schema) plus `--calibrate-rig`, which measures the rig's Quai hashrate and watts and prints the `reference_gpu` block for `research.yaml` (the claim-1 cost-model rig). The USD mining-vs-inference crossover table and all Vast.ai/RunPod market-rate references are gone from the root; benchmark config moved into a `benchmark:` section of `research.yaml`.
- The crossover daemon (`daemon.py`, `report.py`, `test_daemon.py`, its `config.yaml`) moved to `tools/crossover-daemon/` with its own README: a working, tested, USD-denominated utility for Quai miners, explicitly outside the thesis and not evidence for or against it. CI runs its suite from that directory.

### Changed (research pivot)

- The repo is now an empirical test of the energy-money thesis, structured bottom-up around four claims with a built-in null hypothesis and a neutrality contract (see README). The QiCompute marketplace prototype is shelved, frozen, and runnable under `legacy/` (its 241-test suite passes from that directory).
- Claim 1 (`claim1_peg.py`): Qi market price vs modeled energy cost of production (difficulty -> joules/Qi for a reference RTX 3090 x $/kWh), regressed on returns against both the energy model and BTC beta; verdicts are `supports_energy_thesis`, `energy_thesis_not_supported`, or `insufficient_data` below a minimum sample count.
- Claim 2 (`claim2_stability.py`): rolling 30-day volatility of fixed compute bundles (1 kWh; 1M tokens) denominated in USD, BTC, and Qi, with the Qi/joule-vs-Qi/token corollary stated in every output.
- Claim 3: `benchmark.py --store` records tokens/sec, watts, and joules/token with GPU metadata into `measurements.db` (public-dataset schema); `qi_index.py` derives the live "Qi cost of 1M tokens today".
- Claim 4 (`claim4_settlement.py`): minimal escrow/settlement salvaged from QiCompute with audit fixes (integer micro-Qi, WAL, idempotent settle), pricing a job from the live index with conservation checked.
- `fetch_data.py` caches Qi/BTC prices (CoinGecko proposed), Quai difficulty (resumable RPC header sampling or explorer endpoint), and EIA electricity into `data/`; analysis only ever reads the cache. `sample_data.py` generates labeled SYNTHETIC fixtures for offline pipeline tests. `reproduce.py` is the one-command run; `test_claims.py` adds 16 deterministic tests.

### Changed

- Pivot to a minimal provable core: the crossover daemon. `daemon.py` is now a standalone process for Quai GPU miners that prices mining (live Quai price + difficulty feeds, measured hashrate and watts) against open-model inference (live market rate feed or config fallback), computes integer micro-USD net $/day for both, and switches the GPU with hysteresis (margin, consecutive decisions, minimum dwell). On any Quai feed error it defaults to mining. Decisions, samples, and inference request hashes/token-counts are logged to SQLite (WAL, check_same_thread=False, idempotent writes). The marketplace/escrow/committee layers are retained but out of the critical path: the old worker daemon moved to `worker_daemon.py`, its config to `config.marketplace.yaml`.
- `benchmark.py`: one-shot N-minutes-each mining and inference measurement printing the crossover table (hashrate, tokens/sec, watts, net $/day per path).
- `report.py`: renders the SQLite log into `report.md` and `revenue_comparison.png` (daemon revenue vs mining-only revenue, per day).
- `test_daemon.py`: hysteresis/no-flap behavior, dwell, margin floor, feed-failure fallback to mining, integer money math, WAL + idempotent writes, report integration.

### Added

- Energy anchor layer (`energy_anchor.py`): mining-issuance energy parity rate (Qi per joule), energy-anchored job pricing with premium-over-parity reporting, and epoch energy reports comparing settled Qi per joule against the mining parity rate. Documented in `ENERGY_MODEL.md`.
- `energy_anchor` configuration section in `config.yaml` and `config.demo.yaml`; `pricing.estimate_job_price` now derives its energy rate from the anchor when enabled instead of the static `energy_rate_qi_per_joule` value.
- Finalized epochs record `settled_qi_per_joule` in their `energy_totals` metadata.
- `make energy-report` target printing the parity rate and a sample anchored price.
- Tests for the energy anchor layer and first coverage for `market.py`, `runners.py`, and `summary.py` helpers.
- Energy peg stability layer (`energy_peg.py`): smoothed parity oracle with clamped per-epoch steps (replayable from finalized epoch summaries), joule-denominated job quotes converted to Qi only at settlement, stability corridor bounding spot premiums above the energy floor, volatility reporting with stable/volatile verdicts, and a deterministic simulation showing 70%+ Qi cost volatility reduction versus raw token pricing. Configured via the `energy_anchor` section; documented in `ENERGY_MODEL.md`; `make stability-report` target.
- Standardized energy billing (`energy_standards.py`): jobs are billed at a per-model benchmark joules-per-token (`energy_anchor.reference_joules_per_token`) instead of a worker's measured draw, removing the cost-plus incentive to waste energy. Worker efficiency margins and reports against the benchmark, plus clamped benchmark recalibration toward fleet efficiency. `make efficiency-report` target.
- Volume-weighted parity oracle: epochs settling less than `min_epoch_energy_joules` are ignored and oracle influence scales with settled energy up to `full_weight_energy_joules`, so manufacturing thin epochs cannot steer the published rate.
- `stabilized_market_price`: dynamic market pricing from `market_pricing.py` with the stability corridor applied, for quote paths.
- Hardware calibration bridge (`calibrate.py`, `make calibrate`): measures (or accepts) tokens-per-second and watts, derives the recommended `energy_anchor` config values, flags drift beyond 25% against current config, and can append measurements to the evidence registry where the assumption tracker picks them up. Energy parity and billing benchmark assumptions added to `ECONOMIC_ASSUMPTIONS.md`.

### Added (Claim 7, BTC-scale SOAP scenarios, and Claim 6 extension)

- **Claim 7: SOAP adoption rate as energy anchor leading indicator**
  (`claim7_soap_adoption.py`): tracks the fraction of Quai's total effective
  difficulty contributed by SOAP (SHA-256/Scrypt ASIC) workshares over time.
  Computes OLS slope (pp/quarter), R², baseline and latest fraction, and applies
  pre-registered P7 thresholds from `research.yaml → claim7`. Returns
  `soap_adoption_growing`, `soap_adoption_stalled`, `soap_adoption_negligible`,
  or `insufficient_data` (< 90 days post-SOAP-launch). Integrated into
  `reproduce.py` and `REPORT.md`.
- `research.yaml` gains a `claim7:` section: `min_samples` (90),
  `min_growth_pct_per_quarter` (1.0 pp/quarter), `min_latest_fraction` (0.001),
  and `bitcoin_hashrate_ehs` (800.0) for Claim 6 BTC-scale scenario reference.
- `PREDICTIONS.md` gains P7 with numeric failure conditions, data conditions,
  and Bitcoin-scale context note.
- `OBJECTIONS.md` gains objection (l): "Bitcoin miners will never point hashrate
  at Quai — the SOAP incentive is too small" — with Namecoin merge-mining
  precedent and pool-software-support framing.
- `PAPER.md` gains section 4.7 (Claim 7) with results wiring, interpretation
  note, and merge-mining context; objections reference updated to (a)–(l).
- **Claim 6 extended** with `bitcoin_soap_scenarios()`: models dual-revenue
  economics at 0.01%–10% of Bitcoin's ~800 EH/s SHA-256 hashrate (ASIC + GPU
  split configuration). Results appear in `results/claim6.md` and
  `results/claim6_stats.json` under `btc_soap_scenarios`. Includes
  interpretation note linking to Claim 7 as the empirical complement.

### Added (Claim 6, dashboard, and code quality)

- **Claim 6: workshare-for-inference dual-revenue model** (`claim6_workshare_inference.py`):
  models the economics of a GPU that simultaneously mines Quai (submitting KawPoW workshares)
  and serves inference (earning customer payment). Key outputs: expected workshares/day,
  Qi/day from workshare rewards, energy cost in Qi/day, workshare coverage fraction
  (threshold: ≥ 5%), break-even utilisation fraction, and a full sensitivity table across
  4x hashrate range and 50x difficulty range. Integrated into `reproduce.py` and `REPORT.md`.
- `research.yaml` gains a `claim6:` section with pre-registered thresholds:
  `workshare_difficulty_factor`, `block_reward_qi`, `workshares_per_block_target`,
  `coverage_threshold_fraction` (0.05), and `tokens_per_sec_fallback`.
- `PREDICTIONS.md` gains P6 with numeric failure conditions and data conditions.
- `OBJECTIONS.md` gains objection (k): "The dual-revenue model assumes miners can run
  inference simultaneously" — with full treatment of the three valid scenarios (probabilistic
  workshare submission, crossover daemon, and ASIC workshares + GPU inference).
- `PAPER.md` gains sections 4.5 (Claim 5) and 4.6 (Claim 6) with results wiring and
  interpretation notes; Method section updated to describe all six claims; objections
  reference updated to (a)–(j).
- **Live CLI dashboard** (`qi_dashboard.py`): single-screen at-a-glance view of the
  project's current state without running the full pipeline. Shows Qi index, Claim 1
  verdict, Claim 5 sub-verdicts, Claim 6 dual-revenue metrics, data cache freshness for
  all 9 datasets, and pipeline artifact status. Supports `--watch N` for auto-refresh
  every N seconds.
- **7 new deterministic tests** for Claim 6 in `test_claims.py` (40 total): workshare
  scaling, zero-input guards, qi_per_workshare proportionality, energy cost proportionality,
  coverage fraction clamping, model key completeness, verdict validity, and markdown sections.
- `tools/crossover-daemon/telemetry.py` is now a thin shim that loads the root
  `telemetry.py` by absolute path via `importlib.util`, eliminating the duplicate
  implementation. All 14 crossover-daemon tests continue to pass.

## [0.1.0] - 2026-06-03

### Added

- Local worker registry, routing, customer job queue, and LAN controller/worker skeleton.
- Local worker daemon with simulated, subprocess, and Ollama runtime support.
- Privacy-first payload handling with strict mode, controller-blind prompt metadata, and zero-retention runtime behavior.
- Deterministic receipts, receipt hashes, challenge verification, and local verification committees.
- Settlement epochs, customer escrow, worker payable accounts, marketplace treasury accounting, and settlement invoices.
- Abuse resistance simulations for replay attempts, escrow griefing, spam, malicious workers, malicious customers, and committee collusion.
- Load testing, bottleneck reporting, categorized tests, determinism checks, reliability reporting, and CI workflows.

### Security

- Added privacy redaction rules for prompts, raw outputs, private payloads, shared secrets, worker secrets, and runtime responses.
- Added HMAC-signed LAN transport and persistent nonce replay protection for local cluster testing.

### Known Limitations

- Experimental local/LAN prototype only.
- Not a blockchain, wallet, token, payment processor, public network, or production security system.
- Several trust and verification mechanisms are simulation-heavy and protocol-shaped placeholders.
