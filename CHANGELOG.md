# Changelog

All notable changes to QiCompute are documented here. This project follows the spirit of Keep a Changelog and uses semantic versioning for experimental MVP releases.

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
