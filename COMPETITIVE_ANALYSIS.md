# Competitive Analysis

## Summary

QiCompute is strongest where privacy, local control, auditable work records, and idle hardware economics matter. It is weakest where users want simple access, low latency, high model quality, mature support, and guaranteed reliability.

## OpenAI API

Privacy:

- OpenAI offers managed privacy and enterprise controls, but users still send requests to a centralized provider.
- QiCompute can avoid retaining raw prompts locally, but it lacks audited privacy guarantees.

Latency:

- OpenAI is likely better for most users because it has global infrastructure and optimized serving.

Trust:

- OpenAI trust is institutional and contractual.
- QiCompute trust is local/operator-based today.

Verification:

- QiCompute has explicit receipts and useful-work verification concepts.
- OpenAI users usually trust provider execution rather than verify it.

Cost:

- OpenAI has economies of scale.
- QiCompute cost advantage is unproven.

Decentralization:

- OpenAI is centralized.
- QiCompute is not decentralized today, but is more decentralization-shaped.

## Anthropic API

Privacy:

- Similar centralized-provider tradeoff as OpenAI.
- QiCompute may appeal to users who reject remote API processing.

Latency:

- Anthropic likely wins for managed production latency.

Trust:

- Anthropic wins for mature provider trust.
- QiCompute wins only for users who prefer operator-owned infrastructure.

Verification:

- QiCompute has stronger explicit verification modeling.
- Anthropic has stronger operational maturity.

Cost:

- Unknown. QiCompute needs real benchmarks.

Decentralization:

- Anthropic is centralized. QiCompute is currently local/controller-based.

## Local Ollama

Privacy:

- Local Ollama is very strong for privacy because there is no marketplace path.
- QiCompute adds accounting, routing, worker management, and verification around local execution.

Latency:

- Direct Ollama may be faster due to less orchestration.

Trust:

- Direct self-hosting is simpler if the user owns all hardware.
- QiCompute helps when multiple workers, operators, or agents need shared accounting.

Verification:

- QiCompute adds receipts, challenges, committees, and settlement records.
- Ollama alone does not solve marketplace verification.

Cost:

- Direct Ollama has lower overhead for a single user.
- QiCompute must justify overhead with marketplace utility.

Decentralization:

- Ollama is local software, not a market.
- QiCompute is a market prototype.

## GPU Cloud Providers

Privacy:

- GPU clouds offer private instances but still involve cloud vendors.
- QiCompute can target local or region-specific trust.

Latency:

- GPU clouds can be strong if near users and well provisioned.
- QiCompute regional latency is simulated, not measured.

Trust:

- GPU clouds have operational maturity.
- QiCompute relies on local operator trust and prototype controls.

Verification:

- GPU clouds provide rented infrastructure, not proof of useful work.
- QiCompute's verification layer is a differentiator if validated.

Cost:

- GPU clouds expose clear pricing.
- QiCompute pricing is modeled but not market-tested.

Decentralization:

- GPU clouds are centralized businesses.
- QiCompute could become multi-operator, but current state is trusted LAN.

## Decentralized Compute Projects

Privacy:

- Many decentralized compute systems struggle with privacy because work is outsourced.
- QiCompute explicitly prioritizes no raw prompt/output retention, but still needs stronger cryptography.

Latency:

- Decentralized systems often have latency and reliability challenges.
- QiCompute has not proven better latency.

Trust:

- Decentralized projects may have token incentives, staking, or slashing.
- QiCompute intentionally avoids those in this phase, which reduces complexity but leaves trust assumptions unresolved.

Verification:

- QiCompute's useful-work receipt and committee simulation is relevant, but not production proof.

Cost:

- Both sides need real benchmarks. Claims without measured utilization and overhead are weak.

Decentralization:

- QiCompute is less decentralized today than projects with public networks.
- It may be cleaner architecturally because it separates currency issuance from useful-work rewards.

## Brutal Takeaway

QiCompute should not try to beat top APIs on convenience, model quality, or latency in the near term. Its plausible wedge is privacy-first local compute with auditable marketplace accounting for operators who already control hardware.
