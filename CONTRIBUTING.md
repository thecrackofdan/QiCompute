# Contributing

QiCompute is a local-first research prototype. Keep changes small, deterministic, and easy to test.

## Code Style

- Prefer the Python standard library.
- Keep modules focused and readable.
- Avoid heavy dependencies unless there is a clear architectural reason.
- Use structured helpers instead of ad hoc string parsing when possible.

## Privacy Expectations

- Do not persist raw prompts.
- Do not persist raw model outputs.
- Do not log raw prompts or raw outputs.
- Store hashes, token counts, timing, energy, and verification metadata instead.

## Testing Requirements

- Run `python3 -m unittest -v` before submitting changes.
- Add focused tests for new behavior.
- Keep simulations deterministic with explicit seeds or fixed data.

## Protocol Boundaries

- Do not add blockchain, wallet, smart contract, cloud API, or real networking code without a dedicated design pass.
- Keep local protocol-shaped objects simple and auditable.

## Runtime Changes

- Runtime commands must use argument lists and `shell=False`.
- Preserve timeout behavior.
- Keep raw runtime output out of receipts and logs.
