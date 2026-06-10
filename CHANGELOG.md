# Changelog

All notable changes to QiCompute are documented here. This project follows the spirit of Keep a Changelog and uses semantic versioning for experimental MVP releases.

## [Unreleased]

### Added

- Energy anchor layer (`energy_anchor.py`): mining-issuance energy parity rate (Qi per joule), energy-anchored job pricing with premium-over-parity reporting, and epoch energy reports comparing settled Qi per joule against the mining parity rate. Documented in `ENERGY_MODEL.md`.
- `energy_anchor` configuration section in `config.yaml` and `config.demo.yaml`; `pricing.estimate_job_price` now derives its energy rate from the anchor when enabled instead of the static `energy_rate_qi_per_joule` value.
- Finalized epochs record `settled_qi_per_joule` in their `energy_totals` metadata.
- `make energy-report` target printing the parity rate and a sample anchored price.
- Tests for the energy anchor layer and first coverage for `market.py`, `runners.py`, and `summary.py` helpers.

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
