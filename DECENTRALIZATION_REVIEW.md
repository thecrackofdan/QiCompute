# Decentralization Review

## Current State

Actually decentralized today:

- Nothing in the production sense. QiCompute is a local/LAN research prototype.
- Work can execute on separate local workers, but the controller remains trusted.
- Simulations model federation, committees, agent trade, and regional markets, but they do not create real decentralization.

Partially distributed today:

- Controller and worker roles are separated.
- Workers can authenticate, send heartbeats, claim capabilities, poll jobs, execute locally, and submit receipts.
- Job execution can happen away from the controller.

Centralized today:

- Job queue.
- Worker registry.
- Routing decisions.
- Verification decisions.
- Reputation records.
- Escrow accounting.
- Treasury accounting.
- Settlement epoch summaries.
- Audit logs.
- Nonce replay cache.

## Trusted Controller Assumption

The controller is trusted to:

- Hold and update local state.
- Route jobs honestly.
- Enforce leases.
- Accept or reject receipts.
- Record settlement.
- Preserve audit logs.
- Avoid tampering with accounting.

This is acceptable for a trusted LAN prototype. It is not decentralized infrastructure.

## Committee Assumptions

Current state:

- Committees are simulated verification structures.
- Collusion signals are metadata, not enforcement.
- There is no Sybil-resistant verifier admission.

Future vision:

- Independent verifier selection.
- Verifier reputation.
- Dispute resolution.
- Stronger proof of useful work.

## Reputation Assumptions

Current state:

- Reputation is local state controlled by the database/controller.
- It reacts to accepted, failed, rejected, disputed, and stale behavior.

Future vision:

- Reputation may become portable or independently auditable.
- That requires identity, replay protection, dispute handling, and Sybil resistance.

## Settlement Assumptions

Current state:

- Settlement is local SQLite accounting.
- Qi movement is modeled, not executed on a real payment rail.
- QiCompute does not mint Qi.

Future vision:

- Real Qi settlement could bind local marketplace events to external mined Qi.
- That should preserve one issuance mechanism.

## Reality Check

QiCompute is decentralization-ready in shape, not decentralized in fact. The honest description is: local-first private compute marketplace prototype with a trusted controller and simulated decentralization mechanisms.
