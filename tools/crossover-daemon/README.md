# Crossover Daemon (Quai miner utility)

Auto-switches one GPU between **mining Quai** and **serving open-model
inference**, whichever nets more USD/day. Every cycle it prices mining (live
Quai price + network difficulty, your measured hashrate and watts) against
inference (market $/hr rate or config fallback) minus power cost, and
switches with hysteresis so it never flaps. On any Quai feed error it
defaults to mining. Decisions are logged to SQLite; `report.py` renders
"daemon revenue vs mining-only revenue, per day."

```bash
cd tools/crossover-daemon
# edit config.yaml: miner_command, usd_per_kwh, fallback_usd_per_hour
python3 daemon.py            # run (starts your miner, evaluates every 60s)
python3 daemon.py --dry-run  # decide and log only, never touch processes
python3 daemon.py --status   # latest decision
python3 report.py            # report.md + revenue_comparison.png
python3 -m unittest          # 14 tests (hysteresis, feed-failure fallback)
```

**Why this lives in `tools/` and not the repo root:** it is an off-thesis
operational utility, denominated in USD and driven by GPU-rental market
rates. It is useful to a Quai miner today, but it is **not evidence for or
against the energy-money thesis** the repository root tests — it optimizes
revenue in dollars; the research asks whether Qi itself is the right unit of
account. All money math is integer micro-USD/micro-Qi; SQLite uses WAL and
idempotent writes.
