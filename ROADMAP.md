# QiCompute Roadmap

## Current Status

QiCompute v0.1.0 is an experimental MVP for private distributed inference research. It is local-first, LAN-capable, simulation-heavy, and useful for testing receipt-backed useful-work settlement accounting before adding broader networking or decentralized settlement.

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
- Agent accounts with mined, earned, spent, escrowed, and refunded Qi flows

## Agent Economic Participation

Qi is only mined. QiCompute does not mint Qi.

Agents can participate by mining Qi with authorized GPU hardware, earning existing Qi from customers through verified inference, earning existing Qi through verification or infrastructure roles, spending Qi on inference jobs, or receiving Qi from a human/operator account. Humans, agents, and organizations share the same economic layer.

Architecture framing:

```text
Qi = mined currency / settlement asset
QiCompute = inference marketplace using Qi as payment
```

The roadmap keeps issuance separate from marketplace accounting. Agent mining income is recorded from the mining path; marketplace earnings move existing Qi between participants after verification.

One currency. One issuance mechanism. Multiple ways to earn and spend it.

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
- Customer account funding and escrow simulations
- Marketplace treasury fee accounting
- Worker payable balance accounting
- Settlement invoice artifacts
- Accounting reconciliation checks
- Mining fallback profitability comparisons
- Agent policy tuning for mining fallback, inference serving, verification, spending, and idle decisions

## Abuse Resistance Roadmap

- Expand adversarial actor simulations
- Add richer customer reputation and anti-spam policies
- Improve committee collusion analysis
- Persist invoice ledgers for full replay detection
- Replace prototype trust signals with audited security mechanisms before WAN use

## Performance Roadmap

- Keep categorized test runs fast enough for daily development
- Expand synthetic load tests to model larger worker pools and queues
- Add more detailed DB write timing around receipt and settlement hot paths
- Cache route candidates by model and worker availability
- Batch settlement and audit writes under high load
- Replace SQLite with a distributed-ready storage design only after LAN behavior is well measured

## Mining Fallback Roadmap

- Better mining launcher adapters
- More realistic PPLNS simulation
- Clear separation between provisional shares and settled block rewards
