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
- Receipt hashing, validation, challenge verification, and committee simulation
- Reputation updates, retries, expiration, stress simulation, and settlement epochs
- Mining fallback accounting with share and block reward separation

## Planned Runtime Improvements

- Better local Ollama configuration checks
- llama.cpp command/server adapter
- GPU capability probing and model cache awareness
- Safer execution sandbox boundaries

## Verification Roadmap

- Stronger deterministic challenge sets
- Cross-worker duplicate execution checks
- Committee dispute resolution
- Better verifier reputation and slashing simulation

## Networking Roadmap

- Local API boundary after protocol objects stabilize
- Worker-to-router transport
- Authenticated job envelope exchange
- No networking is implemented in the current prototype.

## Privacy Roadmap

- Prompt minimization by default
- Stronger redaction tests
- Private job metadata policies
- Future private settlement integration

## Economic Simulation Roadmap

- Demand cycle models
- Energy price sensitivity
- Worker shutdown thresholds
- Price discovery and utilization metrics

## Mining Fallback Roadmap

- Better mining launcher adapters
- More realistic PPLNS simulation
- Clear separation between provisional shares and settled block rewards
