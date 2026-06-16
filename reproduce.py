"""The skeptic's one command: fetch the data, run every claim, write results/.

    python3 reproduce.py             # real data: fetch (or reuse cache), analyze
    python3 reproduce.py --sample    # SYNTHETIC pipeline demo, no network needed

Real-data mode never substitutes synthetic data: if a dataset is missing and
cannot be fetched, the affected claim reports that and the run says so. The
aggregate verdict lands in results/REPORT.md.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def run(cmd: list[str]) -> int:
    print(f"\n=== {' '.join(cmd)} ===")
    return subprocess.run([sys.executable, *cmd]).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the full claims pipeline")
    parser.add_argument("--sample", action="store_true", help="Synthetic pipeline demo (testing only)")
    parser.add_argument("--skip-fetch", action="store_true", help="Use the existing cache without refetching")
    args = parser.parse_args()
    sample_flag = ["--sample"] if args.sample else []

    if args.sample:
        run(["sample_data.py"])
    elif not args.skip_fetch:
        if run(["fetch_data.py"]) != 0:
            print("\nsome fetches failed; claims will run from whatever cache exists")

    statuses = {
        "claim1_peg": run(["claim1_peg.py", *sample_flag]),
        "claim2_stability": run(["claim2_stability.py", *sample_flag]),
        "qi_index": run(["qi_index.py", *sample_flag]),
        "claim4_settlement": run(["claim4_settlement.py", "--demo", "--db", "settlement.db", *sample_flag]),
    }
    print("\n=== claim 3 (joules/token ground truth) ===")
    print("requires a local GPU + Ollama: python3 benchmark.py --minutes 5 --store")

    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)

    sections = []
    # Single top-level header - individual claim markdowns carry their own
    # SYNTHETIC / DRAFT banners, so we do not duplicate them here.
    sections.append(f"# Qi Energy-Money Claims Report\n\nGenerated {datetime.now(timezone.utc).isoformat()}\n")
    if args.sample:
        sections.append(
            "> **SYNTHETIC SAMPLE DATA** - pipeline demonstration only, not a finding. "
            "All results below are labeled accordingly.\n"
        )

    # Claim 1 one-line verdict summary (extracted from JSON to avoid duplicating
    # the full claim1.md content in the header).
    verdict_path = results_dir / "claim1_stats.json"
    if verdict_path.exists():
        stats = json.loads(verdict_path.read_text(encoding="utf-8"))
        draft = "" if stats.get("thresholds_frozen") else " *(THRESHOLDS DRAFT - not citable)*"
        sections.append(
            f"**Claim 1 verdict: `{stats.get('verdict')}`**{draft} "
            f"- {stats.get('verdict_reason', '')}\n"
        )

    # Include the full markdown output for each claim. Individual claim scripts
    # are responsible for their own SYNTHETIC / DRAFT banners; reproduce.py
    # does not inject additional copies.
    for name in ("claim1.md", "claim2.md"):
        path = results_dir / name
        if path.exists():
            sections.append(path.read_text(encoding="utf-8"))
        else:
            sections.append(
                f"## {name}\n\n"
                "not produced this run (missing data - see console output)\n"
            )

    # Qi index snapshot (claim 3 derived output)
    index_path = results_dir / "qi_index.json"
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        synthetic_note = " *(SYNTHETIC)*" if index.get("synthetic") else ""
        sections.append(
            "## Qi Index (Claim 3 derived)\n\n"
            f"As of **{index.get('as_of', 'unknown')}**{synthetic_note}: "
            f"1 Qi costs **{index.get('qi_cost', '?')} Qi** per "
            f"{index.get('tokens', 1_000_000):,} tokens "
            f"({index.get('joules_per_token_source', '')})\n"
        )
    else:
        sections.append(
            "## Qi Index (Claim 3 derived)\n\n"
            "not produced this run - run `python3 benchmark.py --minutes 5 --store` "
            "on a GPU to populate measurements.db, then rerun.\n"
        )

    # Claim 4 settlement demo receipt
    receipts = sorted(results_dir.glob("receipt_*.json"))
    if receipts:
        receipt = json.loads(receipts[-1].read_text(encoding="utf-8"))
        sections.append(
            "## Claim 4: Settlement Demo\n\n"
            f"Job `{receipt.get('job_id', '?')}` settled via `{receipt.get('settlement_layer', '?')}`. "
            f"Quoted: {receipt.get('quoted_micro_qi', '?')} micro-Qi, "
            f"settled: {receipt.get('settled_micro_qi', '?')} micro-Qi "
            f"({receipt.get('fraction_served', '?')} served). "
            f"Receipt hash: `{receipt.get('receipt_hash', '?')[:16]}...`\n"
        )
    else:
        sections.append(
            "## Claim 4: Settlement Demo\n\n"
            "not produced this run (missing data - see console output)\n"
        )

    failed = [name for name, code in statuses.items() if code != 0]
    if failed:
        sections.append(
            f"\n---\n\nIncomplete this run: {', '.join(failed)} "
            "(missing data or fetch failures - nothing was substituted).\n"
        )

    (results_dir / "REPORT.md").write_text("\n".join(sections), encoding="utf-8")
    print(f"\nreport: results/REPORT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
