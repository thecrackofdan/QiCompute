# Economic Assumptions

Confidence scores are 1 to 5, where 1 means mostly unvalidated and 5 means strongly supported by current evidence.

| Assumption | Why It Matters | Current Evidence | Missing Evidence | Confidence |
| --- | --- | --- | --- | --- |
| Customers value privacy enough to switch providers | Privacy is the main differentiation against centralized APIs | Privacy model, redaction tests, customer demand simulation | User interviews, paid pilots, willingness-to-pay data | 2 |
| Customers will pay for verification | Verification adds cost and complexity | Receipt, challenge, committee, and audit tests | Proof that buyers understand and value verification | 2 |
| Inference beats mining at some demand level | This is the core mining fallback thesis | Crossover and pricing simulations | Real mining profitability, real inference margins, utilization data | 2 |
| Mining can provide a credible worker reservation price | Workers need a fallback income floor | Mining economics model and fallback scheduler | Real authorized mining data and hardware-specific yields | 2 |
| Qi circulates instead of being hoarded | Marketplace utility requires spend and re-spend | Monetary circulation simulation | Real participant treasury behavior | 1 |
| Reputation converges on honest workers | Marketplace quality depends on trust signals | Reputation tests and dynamics simulation | Longitudinal adversarial data | 2 |
| Malicious workers can be excluded | Verification and reputation must block abuse | Duplicate, stale, tampered, rejected, malicious demo tests | Public-network Sybil model and real attack incentives | 2 |
| Good workers are not unfairly penalized | False positives reduce supply and trust | Recovery and false-accusation simulation | Real verifier error rates | 1 |
| Committee systems remain honest enough | Distributed verification depends on committee integrity | Committee consensus simulation and collusion metadata | Sybil resistance, operator identity, incentive compatibility | 1 |
| Agents will spend Qi on useful work | Agent-to-agent economy requires demand from agents | Agent account, escrow, and trade simulations | Real autonomous agent workloads and budgets | 2 |
| Agents will earn Qi by useful services | Agents need a reason to operate workers/verifiers/routers | Agent earning tests and simulations | Real job volume and settlement conversion | 2 |
| Regional compute markets matter | Regional supply can differentiate on latency/privacy | Regional market simulation | Measured latency, regulatory demand, and regional power cost | 2 |
| Privacy-first local execution can coexist with verification | The system needs both privacy and trust | Hash-only receipts, private payload tests | Strong cryptographic proof or trusted execution design | 2 |
| Operators tolerate local-first tooling | Early adoption may depend on self-hosters/operators | CLI demos, LAN setup, tests | Operator onboarding studies | 3 |
| Enterprises accept prototype-style verification | Enterprise demand would be valuable | Architecture and receipt models | Compliance mapping, contracts, support model, auditability | 1 |
| Dynamic prices can clear supply and demand | Marketplace needs workers to choose inference over mining | Pricing model with mining floor | Real price discovery and elasticity | 1 |
| QiCompute can compete on cost | Cost-sensitive buyers need lower total cost | Cost-sensitive scoring model | Benchmark against APIs and GPU clouds | 1 |
| QiCompute can compete on latency | Latency-sensitive buyers may reject distributed routing | Routing model and regional simulation | End-to-end latency measurements | 1 |
| Local controller trust is acceptable for early markets | Current architecture is not public decentralized | LAN controller prototype and docs | Clear target customer willing to trust operator | 3 |
| Useful work should not mint Qi | Avoids second issuance path and incentive confusion | Strong doc/code principle | Economic analysis of reward sufficiency | 4 |
| Mining issuance yields a usable energy parity rate | The energy anchor and peg derive all pricing from Qi per joule | Parity, oracle, corridor, and peg simulations with deterministic tests | Real mining yield and wall-socket energy measurements | 1 |
| Reference joules per token reflects real model energy use | Standardized billing depends on credible per-model benchmarks | Placeholder benchmark table and calibration tooling | Hardware benchmark measurements across GPUs and models | 1 |

## Highest Priority Evidence To Gather

1. Real customer interviews and paid trials for privacy-sensitive and self-hosted users.
2. Hardware measurements comparing mining fallback with model serving revenue.
3. Verification accuracy under realistic model output variance and malicious behavior.
4. Operator willingness to run LAN/local infrastructure.
5. Qi circulation behavior in simulated and real closed pilots.
