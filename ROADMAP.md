# QiCompute Roadmap

QiCompute is currently:

- local-first
- experimental
- simulation-heavy
- not production-ready
- not a blockchain

## Current Prototype Capabilities

- Local worker registry and job routing
- Runtime daemon with simulated, subprocess, and local Ollama support
- Local LAN controller/worker skeleton with signed messages
- Worker enrollment, persistent nonce replay protection, and job leases
- Operator CLIs for enrollment, health, cluster inspection, and smoke testing
- Receipt hashing, validation, challenge verification, and committee simulation
- Reputation updates, retries, expiration, stress simulation, and settlement epochs
- Mining fallback accounting with share and block reward separation

## Planned Runtime Improvements

- Better local Ollama configuration checks
- llama.cpp command/server adapter
- GPU capability probing and model cache awareness
- Safer execution sandbox boundaries
- More accurate runtime slot accounting across real model runners

## Verification Roadmap

- Stronger deterministic challenge sets
- Cross-worker duplicate execution checks
- Committee dispute resolution
- Better verifier reputation and slashing simulation

## Networking Roadmap

- Harden local LAN controller/worker transport
- Add safer prompt transfer policies
- Add worker-to-router transport
- Authenticated job envelope exchange
- Current networking is limited to local/LAN HTTP skeletons with shared-secret HMAC. There is no public networking.
- Current cluster mode is a trusted-controller prototype, not decentralized consensus.

## Decentralization Readiness Roadmap

- Replace trusted-controller assignment with replicated coordination
- Expand per-worker enrollment into decentralized identity
- Make controller snapshots importable for failover
- Add committee anti-collusion policies beyond operator/region diversity
- Keep private prompts and raw outputs out of shared settlement state

## Privacy Roadmap

- Strict privacy mode by default
- Prototype private payload envelopes with hashes
- Controller-blind prompt handling for LAN jobs
- Zero-retention runtime metadata for subprocess and Ollama
- Stronger redaction tests for prompts, outputs, keys, and worker secrets
- Future private settlement integration
- Replace local prototype encryption with audited production cryptography before WAN use

## Economic Simulation Roadmap

- Demand cycle models
- Energy price sensitivity
- Worker shutdown thresholds
- Price discovery and utilization metrics

## Mining Fallback Roadmap

- Better mining launcher adapters
- More realistic PPLNS simulation
- Clear separation between provisional shares and settled block rewards
