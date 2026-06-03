# QiCompute MVP Definition

## What Is QiCompute Today?

QiCompute is a local-first experimental MVP for a privacy-first distributed inference marketplace. It models useful-work verification, local worker trust, and settlement accounting before adding public networking or blockchain integration.

## Included

- Private job handling with prompt hashes and private payload envelopes.
- Local inference execution through simulated, subprocess, and Ollama runtimes.
- LAN controller/worker workflow with enrollment, authentication, leases, and reassignment.
- Receipt hashing, challenge verification, and local committee verification.
- Settlement epochs, customer escrow, worker payables, treasury accounting, and invoices.
- Abuse simulation, replay resistance, rate limits, audit tooling, and reconciliation checks.
- Operator tooling, demos, smoke tests, load tests, reliability reports, and CI workflows.

## Not Included

- Blockchain integration.
- Token issuance or transfer.
- Wallets or payment processing.
- Public networking.
- Production cryptography.
- Production consensus.
- Audited security guarantees.

## Purpose

The MVP exists to make the architecture concrete and testable:

```text
private job -> local execution -> useful-work verification -> settlement accounting
```

It is a research and development platform, not production infrastructure.
