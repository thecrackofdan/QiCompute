# Changelog

All notable changes to QiCompute are documented here. This project follows the spirit of Keep a Changelog and uses semantic versioning for experimental MVP releases.

## [Unreleased]

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
