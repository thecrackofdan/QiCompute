# Customer Fit

## Privacy-Conscious Users

Pain points:

- Do not want prompts retained by centralized providers.
- Need local or region-aware execution.
- May lack skill to self-host reliably.

Why QiCompute helps:

- Strict privacy defaults store hashes, counts, timing, and receipts instead of raw prompts and outputs.
- Local worker execution can be inspected by the operator.
- Verification and receipts create an audit trail.

Why they may reject it:

- No production cryptography or audited privacy guarantees yet.
- Trusted controller remains a meaningful trust point.
- Local setup may be more work than using an API.

Adoption barriers:

- Need simple deployment, clear threat model, and concrete privacy guarantees.

## Local Businesses

Pain points:

- Want local AI workflows without sending sensitive data to remote APIs.
- May need predictable cost and basic auditability.

Why QiCompute helps:

- LAN-first architecture can keep work inside an owned environment.
- Escrow and settlement accounting can explain costs.

Why they may reject it:

- Support, reliability, compliance, and model quality are not production-grade.
- They may prefer managed SaaS.

Adoption barriers:

- Need packaged deployment, operator docs, support process, and real reliability metrics.

## Enterprises

Pain points:

- Data governance, auditability, regional restrictions, vendor risk.

Why QiCompute helps:

- The architecture is privacy- and audit-shaped.
- Receipts, invoices, epochs, and snapshots are useful concepts.

Why they may reject it:

- No audited cryptography, compliance program, SOC2-style controls, procurement path, or production support.
- Trusted LAN controller is not enough for cross-organization trust.

Adoption barriers:

- Very high. Enterprise should be treated as a future validation target, not the first customer.

## AI Agents

Pain points:

- Need compute for autonomous workflows.
- May need to earn and spend in the same economic layer.

Why QiCompute helps:

- Agent accounts, escrow, earning, spending, and policy simulation directly model this.
- Agent-to-agent trade is a natural fit for programmable demand.

Why they may reject it:

- Real agents need reliable APIs, predictable settlement, and available supply.
- There is no real wallet or public network.

Adoption barriers:

- Need a contained pilot where agents operate under human-controlled accounts.

## Researchers

Pain points:

- Need affordable batch inference, reproducibility, and local privacy.

Why QiCompute helps:

- Deterministic receipts and local execution records can support reproducible accounting.
- Bulk/batch demand can tolerate latency.

Why they may reject it:

- GPU clouds may be simpler and more powerful.
- Model availability and performance are not proven.

Adoption barriers:

- Need benchmarks, supported model matrix, and cost comparisons.

## Self-Hosters

Pain points:

- Own hardware but have idle GPU time.
- Want privacy and control.

Why QiCompute helps:

- Mining fallback plus inference marketplace is most aligned with this group.
- Local-first tooling and CLI demos match self-hoster expectations.

Why they may reject it:

- If they can self-host directly, marketplace overhead may not help.
- Mining fallback only matters if Qi mining is real and profitable.

Adoption barriers:

- Need simple worker setup, clear earnings model, and evidence that inference jobs arrive.

## Best Early Fit

The most realistic early users are self-hosters, privacy-conscious technical users, and local operators. Enterprise adoption is possible only after the trust, compliance, support, and production-readiness gaps are narrowed.
