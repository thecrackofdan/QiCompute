# QiCompute Showcase

Run these commands from a local checkout:

```bash
python3 doctor.py
python3 demo.py --mode honest
python3 cluster_demo.py --workers 3 --jobs 10
python3 cluster_health.py
python3 reliability_report.py
```

## Expected Outputs

`doctor.py` prints local environment checks for Python, SQLite, config shape, runtime config, DB writability, and optional Ollama availability.

`demo.py --mode honest` runs a local end-to-end useful-work path: job submission, routing, runtime execution, receipt creation, challenge verification, committee verification, payout eligibility, and epoch summary.

`cluster_demo.py --workers 3 --jobs 10` simulates a small LAN cluster with multiple worker identities, job assignment, receipt submission, verification, and settlement totals.

`cluster_health.py` prints controller/worker health: worker counts, job counts, lease state, recent failures, active epoch, and settlement totals.

`reliability_report.py` prints PASS/WARN/FAIL style reliability signals for test counts, simulation success, abuse detection, replay prevention, and settlement reconciliation.

No command should print raw prompts or raw model outputs.
