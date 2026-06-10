# Security Policy

## Supported Versions

QiCompute is experimental. The current supported prototype version is:

| Version | Supported |
| ------- | --------- |
| 0.1.0   | Yes       |

## Responsible Disclosure

Please do not publicly disclose a suspected security issue before maintainers have had a reasonable chance to respond. Open a security report using the GitHub security issue template or contact the project maintainer through the repository owner profile.

Include:

- affected component
- reproduction steps
- expected impact
- whether prompts, outputs, secrets, receipts, or accounting state may be exposed

## Privacy Considerations

QiCompute is designed to avoid storing raw prompts and raw model outputs by default. Reports, logs, snapshots, fixtures, and CI artifacts should contain only aggregate metrics, hashes, and redacted metadata.

## Prototype Limitations

QiCompute is experimental and not production security infrastructure. It is not audited, not production E2E encryption, not a wallet, not a blockchain, and not suitable for hostile public networks.

Do not use QiCompute to process sensitive production data.
