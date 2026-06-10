"""Render the daemon's SQLite log into one chart and one summary.

    python3 report.py                # writes report.md + revenue_comparison.png

The comparison: revenue the daemon's switching actually earned per day versus
what mining-only would have earned over the same hours. Both series integrate
the per-day net rates logged with each decision, in integer micro-USD.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any

from daemon import SECONDS_PER_DAY, CrossoverDB, MODE_MINING, micro_to_str


MAX_GAP_SECONDS = 600  # daemon downtime between decisions earns nothing


def daily_revenue(decisions: list[dict[str, Any]], *, max_gap_seconds: int = MAX_GAP_SECONDS) -> dict[str, dict[str, int]]:
    """Integrate decision intervals into per-day daemon vs mining-only revenue.

    Each decision row carries the net $/day rates that held until the next
    decision. Gaps longer than ``max_gap_seconds`` (daemon stopped) contribute
    nothing to either series.
    """
    days: dict[str, dict[str, int]] = {}
    for current, nxt in zip(decisions, decisions[1:]):
        started = datetime.fromisoformat(current["ts"])
        ended = datetime.fromisoformat(nxt["ts"])
        seconds = min(max(int((ended - started).total_seconds()), 0), max_gap_seconds)
        if seconds <= 0:
            continue
        day = started.date().isoformat()
        bucket = days.setdefault(day, {"daemon_usd_micro": 0, "mining_only_usd_micro": 0, "seconds": 0})
        active_rate = (
            current["mining_net_usd_micro_per_day"]
            if current["mode_after"] == MODE_MINING
            else current["inference_net_usd_micro_per_day"]
        )
        bucket["daemon_usd_micro"] += active_rate * seconds // SECONDS_PER_DAY
        bucket["mining_only_usd_micro"] += current["mining_net_usd_micro_per_day"] * seconds // SECONDS_PER_DAY
        bucket["seconds"] += seconds
    return days


def render_markdown(days: dict[str, dict[str, int]]) -> str:
    lines = [
        "# Crossover Daemon Revenue Report",
        "",
        "| Day | Hours logged | Daemon $ | Mining-only $ | Daemon advantage $ |",
        "| --- | --- | --- | --- | --- |",
    ]
    total_daemon = 0
    total_mining = 0
    for day in sorted(days):
        bucket = days[day]
        advantage = bucket["daemon_usd_micro"] - bucket["mining_only_usd_micro"]
        total_daemon += bucket["daemon_usd_micro"]
        total_mining += bucket["mining_only_usd_micro"]
        lines.append(
            f"| {day} | {bucket['seconds'] / 3600:.1f} | {micro_to_str(bucket['daemon_usd_micro'])} "
            f"| {micro_to_str(bucket['mining_only_usd_micro'])} | {micro_to_str(advantage)} |"
        )
    lines += [
        "",
        f"**Total: daemon ${micro_to_str(total_daemon)} vs mining-only ${micro_to_str(total_mining)} "
        f"(advantage ${micro_to_str(total_daemon - total_mining)})**",
        "",
    ]
    return "\n".join(lines)


def render_chart(days: dict[str, dict[str, int]], path: str) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    labels = sorted(days)
    daemon_usd = [days[day]["daemon_usd_micro"] / 1e6 for day in labels]
    mining_usd = [days[day]["mining_only_usd_micro"] / 1e6 for day in labels]
    positions = range(len(labels))
    width = 0.38
    fig, ax = plt.subplots(figsize=(max(6, len(labels) * 1.2), 4.5))
    ax.bar([p - width / 2 for p in positions], daemon_usd, width, label="daemon (switching)")
    ax.bar([p + width / 2 for p in positions], mining_usd, width, label="mining-only")
    ax.set_xticks(list(positions))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylabel("net USD per day")
    ax.set_title("Daemon revenue vs mining-only revenue")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Crossover daemon revenue report")
    parser.add_argument("--db", default="crossover.db")
    parser.add_argument("--out-markdown", default="report.md")
    parser.add_argument("--out-chart", default="revenue_comparison.png")
    args = parser.parse_args()
    db = CrossoverDB(args.db)
    decisions = db.decisions()
    db.close()
    if len(decisions) < 2:
        print("not enough decisions logged yet; run the daemon first")
        return 1
    days = daily_revenue(decisions)
    markdown = render_markdown(days)
    with open(args.out_markdown, "w", encoding="utf-8") as handle:
        handle.write(markdown)
    print(markdown)
    if render_chart(days, args.out_chart):
        print(f"chart written to {args.out_chart}")
    else:
        print("matplotlib not installed; skipped the chart (pip install matplotlib)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
