# QiCompute 0.1.0 Release Notes

QiCompute 0.1.0 is an experimental MVP for a privacy-first distributed inference marketplace prototype with useful-work verification and local settlement accounting.

## What Works

- Local inference-first worker behavior with mining fallback accounting.
- Local runtime execution through simulated, subprocess, and Ollama adapters.
- LAN controller/worker skeleton with enrollment, HMAC authentication, replay protection, job leases, and reassignment.
- Receipt generation, deterministic receipt hashes, challenge verification, and local verification committees.
- Customer escrow, worker payable balances, marketplace treasury accounting, settlement epochs, and invoices.
- Abuse simulations, rate limits, audit reports, load tests, bottleneck reports, determinism checks, and reliability reports.

## Architecture Overview

```text
customer job -> routing -> daemon/runtime -> receipt -> challenge verification
-> committee verification -> escrow settlement -> epoch summary
```

The current architecture is LAN-first and controller-mediated. It prepares boundaries for decentralized routing and settlement later, but does not implement decentralized consensus today.

## Privacy Model

Strict privacy mode is the default. QiCompute stores prompt hashes, private payload envelopes, output hashes, counts, timings, and accounting metadata. It should not persist raw prompts or raw model outputs by default.

Prototype encryption and HMAC transport are local development mechanisms, not audited production cryptography.

## Marketplace Accounting

QiCompute simulates a marketplace ledger locally:

- customer available and escrowed balances
- job escrow lifecycle
- worker payable accounting
- marketplace treasury fees and refunds
- settlement invoices and epoch summaries

No real token transfers, wallets, blockchain settlement, or payment processing are included.

## Testing

The release includes categorized tests, smoke CI, full validation CI, performance/load tooling, determinism checks, and reliability reporting.

## Known Limitations

- LAN-first, not public internet infrastructure.
- Controller is trusted in current cluster mode.
- Verification committees and challenges are local simulations.
- Cryptography is placeholder-level except for hashes and HMAC transport.
- SQLite is used for local prototype storage.
- Not production-ready and not audited.

## Future Directions

- Safer real runtime sandboxing.
- Stronger useful-work verification.
- Better model locality and scheduling.
- Decentralized coordination and settlement research.
- Production-grade cryptography before any WAN use.
