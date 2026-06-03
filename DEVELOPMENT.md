# QiCompute Development Guide

QiCompute values deterministic behavior over maximum speed. The project is simulation-heavy, accounting-heavy, and privacy-sensitive, so development workflows are designed to catch drift early without forcing every edit loop to run the full suite.

## Current Status

QiCompute v0.1.0 is an experimental MVP. Development should preserve clear prototype boundaries: no production security claims, no public networking assumptions, no blockchain settlement, and no raw prompt/output persistence.

Version metadata lives in `VERSION`. Release readiness can be checked with:

```bash
python3 release_check.py
python3 license_check.py
```

## Test Categories

Run smoke tests for quick contributor feedback:

```bash
python3 run_tests.py --smoke
```

Run focused suites:

```bash
python3 run_tests.py --unit
python3 run_tests.py --integration
python3 run_tests.py --simulation
python3 run_tests.py --slow
python3 run_tests.py --all
```

Validate categorization:

```bash
python3 run_tests.py --validate-categories
```

Every discovered test is assigned at least one category by the test runner. Smoke tests are intentionally small and fast. Simulation and slow tests may run longer.

## Profiling Tests

Use profiling when the suite starts feeling slower:

```bash
python3 run_tests.py --all --profile
```

The profile output lists total runtime, average runtime, slowest tests, and slowest suites.

## CI Workflows

`.github/workflows/smoke.yml` runs compile checks, smoke tests, and category validation on Python 3.10, 3.11, and 3.12.

`.github/workflows/full_validation.yml` runs the full test suite, accounting checks, load-test sanity, bottleneck reporting, reliability reporting, and uploads aggregate CI artifacts.

Artifacts contain only aggregate metrics. They must not contain prompts, raw model outputs, private payloads, worker secrets, or shared secrets.

## Determinism Philosophy

Simulation output should be reproducible when given the same seed. Use:

```bash
python3 determinism.py
```

The determinism checks compare seeded simulation, epoch/load summaries, and invoice hashes.

## Fixture Philosophy

Fixtures in `fixtures/` are sanitized reference outputs for epoch summaries, invoices, controller snapshots, settlement examples, and load-test samples. They are intentionally small and do not include raw prompts or raw outputs.

Use fixtures to detect accidental behavioral drift in accounting, privacy, or summary shape. Do not store sensitive payloads in fixtures.

## Reliability Reports

Generate a local reliability summary:

```bash
python3 reliability_report.py
```

The report summarizes test counts, simulation success, abuse detection, settlement reconciliation, replay prevention, committee dispute counts, and warnings.

## Development Health

Use the console health dashboard before larger changes:

```bash
python3 dev_health.py
```

It runs smoke tests, a small load test, bottleneck reporting, quick accounting, and reliability checks.
