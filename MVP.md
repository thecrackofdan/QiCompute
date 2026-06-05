# QiCompute MVP Definition

## What Is QiCompute Today?

QiCompute is a local-first experimental MVP for a privacy-first distributed inference marketplace. It models useful-work verification, local worker trust, and settlement accounting before adding public networking or blockchain integration.

## Included

- Private job handling with prompt hashes and private payload envelopes.
- Local inference execution through simulated, subprocess, and Ollama runtimes.
- LAN controller/worker workflow with enrollment, authentication, leases, and reassignment.
- Receipt hashing, challenge verification, and local committee verification.
- Settlement epochs, customer escrow, worker payables, treasury accounting, and invoices.
- Agent accounts for mined, earned, spent, escrowed, and refunded Qi flows.
- Abuse simulation, replay resistance, rate limits, audit tooling, and reconciliation checks.
- Operator tooling, demos, smoke tests, load tests, reliability reports, and CI workflows.

## Agent Economic Participation

Qi is only mined. QiCompute does not mint Qi.

Architecture framing:

```text
Qi = mined currency / settlement asset
QiCompute = inference marketplace using Qi as payment
```

Agents do not mint Qi because they are agents. They can acquire Qi by mining with authorized GPU hardware, earning existing Qi from customers by serving verified inference, earning existing Qi through verification or infrastructure roles, or receiving Qi from a human/operator account.

Agents can spend Qi on inference jobs through local escrow. Successful jobs spend reserved Qi; failed jobs refund reserved Qi. Agents operating workers can earn Qi only when worker receipts are verified, and duplicate receipts do not double-credit earnings.

Humans, agents, and organizations share the same economic layer.

One currency. One issuance mechanism. Multiple ways to earn and spend it.

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
