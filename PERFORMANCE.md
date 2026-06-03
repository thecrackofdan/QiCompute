# QiCompute Performance Guide

QiCompute is still a local-first SQLite prototype. The performance tools are meant to answer practical operator and developer questions before moving to larger storage or distributed coordination.

## Test Suites

Run the full compatibility suite:

```bash
python3 -m unittest -v
```

Run categorized suites:

```bash
python3 run_tests.py --unit
python3 run_tests.py --integration
python3 run_tests.py --simulation
python3 run_tests.py --all
```

Use unit tests during tight edit loops. Use integration tests before changing controller, daemon, runtime, cluster, settlement, or transport behavior. Use simulation tests before changing routing, stress, economics, or demo flows.

## Load Tests

Run synthetic controller load with simulated workers and runtime:

```bash
python3 load_test.py --workers 10 --jobs 100
python3 load_test.py --workers 50 --jobs 1000 --mode mixed --seed 42
```

The load test reports submitted/completed/failed jobs, throughput, route and execution latency percentiles, settlement totals, refund totals, attack counters, and database size. It never prints raw prompts or model outputs.

## Bottleneck Reports

```bash
python3 bottleneck_report.py --workers 25 --jobs 500
```

The report breaks down routing, DB write, verification, committee, settlement, execution, and total runtime. The recommendation field points to the highest cumulative stage.

## Accounting Checks

Quick checks use aggregate reconciliation and are suitable for frequent load runs:

```bash
python3 accounting_checks.py --quick
```

Full checks include replay, duplicate payout, and stale receipt checks:

```bash
python3 accounting_checks.py --full
```

## Expected Local Ranges

On a typical developer machine, small simulated runs should complete in seconds. Real Ollama runtime throughput depends on model size, GPU memory, model warm-cache behavior, and local energy telemetry availability.

SQLite is acceptable for the LAN prototype because it keeps setup simple and deterministic. It is not the final storage layer for decentralized-scale operation. Larger deployments will need batched writes, queue partitioning, and replicated state.

## Scale Roadmap

Near-term performance work:

- batch controller writes for high-throughput receipt submission
- cache online workers by supported model
- reduce repeated committee metadata reads
- add bounded worker-side queues
- move long-running runtime execution away from controller hot paths
