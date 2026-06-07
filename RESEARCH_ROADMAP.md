# Research Roadmap

## Next 3 Months

Focus: validate demand and crossover economics.

- Interview privacy-conscious users, self-hosters, local businesses, and researchers.
- Run small paid or commitment-based pilots before adding infrastructure.
- Measure mining versus inference on real GPUs.
- Build a benchmark matrix for models, throughput, watts, latency, and failure rate.
- Test whether users understand and value receipts/verification.
- Record operator setup time and friction.
- Refine economic simulations only when new measurements justify changes.

Success criteria:

- At least one customer segment shows concrete willingness to pay.
- At least one hardware/model combination shows inference can beat mining under plausible demand.
- Operators can run the local stack without developer assistance.

## Next 6 Months

Focus: validate trust, privacy, and operations.

- Run a closed trusted-operator pilot.
- Measure real job queue behavior, utilization, refunds, and settlement reconciliation.
- Test malicious, flaky, and recovering worker behavior with realistic workloads.
- Define data responsibility, retention, and regional privacy requirements.
- Compare real costs against OpenAI, Anthropic, local Ollama, and GPU clouds.
- Decide whether the first market is self-hosters, local businesses, agents, or researchers.

Success criteria:

- Real workload data improves or invalidates the pricing and circulation models.
- Verification overhead is measured.
- Trust assumptions are documented for the actual pilot users.

## Next 12 Months

Focus: decide whether productionization is justified.

- Decide whether to continue, narrow, or stop based on evidence.
- If continuing, design production security and settlement paths from measured requirements.
- Do not add public networking until trusted-controller pilots show real demand.
- Do not add chain settlement until local accounting has proven value.
- Explore stronger cryptography or independent verification only if privacy and verification demand are validated.

Success criteria:

- Clear customer segment.
- Clear economic crossover data.
- Clear operator economics.
- Clear trust model.
- Clear reason to invest in production systems.
