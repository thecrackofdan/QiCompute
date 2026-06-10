# Production Gaps

## Security Gaps

| Gap | Severity | Difficulty | Recommended Mitigation |
| --- | --- | --- | --- |
| Trusted LAN controller is central authority | High | High | Define threat model, separate controller roles, add independent audit and failover before public use |
| Shared-secret/HMAC transport is not public-network security | High | Medium | Use modern mutual authentication, key rotation, and audited protocol design |
| Prototype private payload envelope is not audited cryptography | High | High | Replace with reviewed encryption design and external security review |
| Sybil resistance is absent | High | High | Define identity, operator admission, verifier selection, and abuse economics |
| Committee collusion only simulated | High | High | Add real adversarial testing and committee independence requirements |

## Scalability Gaps

| Gap | Severity | Difficulty | Recommended Mitigation |
| --- | --- | --- | --- |
| SQLite is local and controller-bound | Medium | Medium | Keep SQLite for MVP; define migration path only after validating demand |
| Single controller owns queue, registry, and settlement | High | High | Validate with trusted operators first; avoid premature distributed systems work |
| Simulated demand does not stress real model serving | Medium | Medium | Run measured load tests with real runtimes and GPUs |
| Worker discovery and routing are local | Medium | Medium | Measure local/LAN performance before adding public routing |

## Operational Gaps

| Gap | Severity | Difficulty | Recommended Mitigation |
| --- | --- | --- | --- |
| No production deployment path | Medium | Medium | Create pilot-only operator runbook, not cloud deployment yet |
| No support, incident, or recovery process | Medium | Medium | Add operational playbooks after first pilot |
| Model availability and cache behavior are under-specified | Medium | Medium | Build a supported model matrix and runtime benchmark report |
| No real billing or payout operations | High | High | Keep research local until settlement path is defined |

## Legal And Privacy Concerns

| Gap | Severity | Difficulty | Recommended Mitigation |
| --- | --- | --- | --- |
| Data processing responsibilities are undefined | High | Medium | Map controller, worker, customer, and operator responsibilities |
| Regional privacy claims are simulated | Medium | Medium | Tie regional routing to real legal requirements before making claims |
| No retention policy beyond prototype behavior | Medium | Low | Formalize retention and deletion policy |
| No enterprise compliance controls | High | High | Do not target enterprise production until controls exist |

## Economic Risks

| Gap | Severity | Difficulty | Recommended Mitigation |
| --- | --- | --- | --- |
| Demand is unproven | High | Medium | Run customer discovery and paid pilots before more infrastructure |
| Mining fallback profitability is unmeasured | High | Medium | Measure hardware-specific mining and inference crossover |
| Qi circulation may stagnate | High | Medium | Track spending, hoarding, and reinvestment in closed simulations/pilots |
| Verification may cost more than buyers will pay | Medium | Medium | Benchmark verification overhead and buyer willingness to pay |
