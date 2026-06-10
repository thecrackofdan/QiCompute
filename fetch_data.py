"""Fetch and cache the public data behind the claims.

    python3 fetch_data.py            # fetch whatever is missing
    python3 fetch_data.py --force    # refetch everything

Each dataset is written to data/<name>.json as
{"fetched_at": ..., "source": ..., "synthetic": false, "series": {date: value}}.
Analysis scripts only ever read the cache, so a skeptic can inspect exactly
the data a result was computed from. Fetch failures leave existing caches
untouched and are reported, never papered over.
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml  # type: ignore


def load_research_config(path: str = "research.yaml") -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def http_get_json(url: str, timeout: float = 30.0) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "qi-energy-money-research"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def http_post_json(url: str, payload: dict[str, Any], timeout: float = 30.0) -> Any:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "qi-energy-money-research"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def dig(data: Any, path: str) -> Any:
    current = data
    for part in path.split("."):
        if not part:
            continue
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


def ms_to_date(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).date().isoformat()


def pairs_to_daily(pairs: list[list[float]]) -> dict[str, float]:
    """Collapse [[ms_epoch, value], ...] to one value per UTC date (last wins)."""
    series: dict[str, float] = {}
    for ms, value in pairs:
        series[ms_to_date(float(ms))] = float(value)
    return series


def write_cache(data_dir: Path, name: str, series: dict[str, float], source: str, *, synthetic: bool = False) -> Path:
    """Write a dataset as JSON (with provenance) plus a CSV mirror for inspection."""
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / f"{name}.json"
    ordered = dict(sorted(series.items()))
    payload = {
        "fetched_at": "synthetic" if synthetic else datetime.now(timezone.utc).isoformat(),
        "source": source,
        "synthetic": synthetic,
        "series": ordered,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    csv_lines = ["date,value"] + [f"{date},{value}" for date, value in ordered.items()]
    (data_dir / f"{name}.csv").write_text("\n".join(csv_lines) + "\n", encoding="utf-8")
    return path


def read_cache(data_dir: Path, name: str) -> dict[str, Any] | None:
    path = data_dir / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_price(config: dict[str, Any], data_dir: Path, name: str, url_key: str) -> str:
    prices_cfg = config["prices"]
    url = prices_cfg[url_key]
    data = http_get_json(url)
    pairs = dig(data, prices_cfg.get("json_path", "prices"))
    series = pairs_to_daily(pairs)
    if len(series) < 2:
        raise ValueError(f"{name}: feed returned {len(series)} points")
    write_cache(data_dir, name, series, url)
    extra = ""
    if name == "qi_usd":
        # liquidity context for OBJECTIONS.md: thin volume is a finding, not a problem to hide
        try:
            volumes = pairs_to_daily(dig(data, prices_cfg.get("volume_json_path", "total_volumes")))
            write_cache(data_dir, "qi_volume_usd", volumes, url)
            extra = f"; volume series: {len(volumes)} points"
        except Exception as exc:
            extra = f"; volume series unavailable ({type(exc).__name__})"
    return f"{name}: {len(series)} daily points{extra}"


def fetch_difficulty(config: dict[str, Any], data_dir: Path) -> str:
    """Difficulty history: explorer endpoint first, RPC header sampling as fallback.

    mode "explorer": explorer only (fails loudly). mode "rpc_scan": RPC only.
    mode "both": try the explorer for deep history; on any error, report it
    and fall back to RPC sampling.
    """
    diff_cfg = config["difficulty"]
    mode = str(diff_cfg.get("mode", "both"))
    if mode in {"explorer", "both"} and diff_cfg.get("explorer_url"):
        try:
            return _fetch_difficulty_explorer(diff_cfg, data_dir)
        except Exception as exc:
            if mode == "explorer":
                raise
            print(f"difficulty: explorer failed ({type(exc).__name__}: {exc}); falling back to rpc scan")
    elif mode == "explorer":
        raise ValueError("difficulty.mode is 'explorer' but explorer_url is not configured")
    return fetch_difficulty_rpc_scan(diff_cfg, data_dir)


def _fetch_difficulty_explorer(diff_cfg: dict[str, Any], data_dir: Path) -> str:
    data = http_get_json(diff_cfg["explorer_url"])
    pairs = dig(data, diff_cfg.get("explorer_json_path", ""))
    series = pairs_to_daily([[p[0], float(p[1])] for p in pairs])
    if len(series) < 2:
        raise ValueError(f"explorer returned {len(series)} points")
    write_cache(data_dir, "difficulty", series, diff_cfg["explorer_url"])
    return f"difficulty: {len(series)} points (explorer)"


def fetch_difficulty_rpc_scan(diff_cfg: dict[str, Any], data_dir: Path) -> str:
    """Sample block headers back through the chain via JSON-RPC.

    Resumes from the existing cache, so repeated runs extend history cheaply.
    """
    url = diff_cfg["rpc_url"]
    step = max(int(diff_cfg.get("rpc_block_step", 3000)), 1)
    difficulty_path = diff_cfg.get("rpc_difficulty_path", "result.woHeader.difficulty")
    timestamp_path = diff_cfg.get("rpc_timestamp_path", "result.woHeader.timestamp")

    head = http_post_json(url, {"jsonrpc": "2.0", "id": 1, "method": "quai_blockNumber", "params": []})
    head_number = int(str(dig(head, "result")), 16)

    existing = read_cache(data_dir, "difficulty")
    series: dict[str, float] = dict(existing["series"]) if existing else {}
    sampled = 0
    for number in range(head_number, 0, -step):
        block = http_post_json(
            url,
            {"jsonrpc": "2.0", "id": 1, "method": "quai_getBlockByNumber", "params": [hex(number), False]},
        )
        raw_difficulty = dig(block, difficulty_path)
        raw_timestamp = dig(block, timestamp_path)
        difficulty = int(str(raw_difficulty), 16) if str(raw_difficulty).startswith("0x") else int(raw_difficulty)
        timestamp = int(str(raw_timestamp), 16) if str(raw_timestamp).startswith("0x") else int(raw_timestamp)
        date = datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()
        if date in series:
            break  # cache already covers from here back
        series[date] = float(difficulty)
        sampled += 1
        if sampled >= 400:  # cap one run's RPC load; rerun to extend
            break
    if not series:
        raise ValueError("difficulty: rpc scan produced no samples")
    write_cache(data_dir, "difficulty", series, f"{url} (rpc_scan step={step})")
    return f"difficulty: {len(series)} daily points ({sampled} new via rpc)"


def fetch_electricity(config: dict[str, Any], data_dir: Path) -> str:
    elec_cfg = config["electricity"]
    key = str(elec_cfg.get("eia_api_key", "") or "")
    if not key:
        return "electricity: no EIA API key configured; claim 2 will use the flat fallback"
    url = elec_cfg["eia_url_template"].format(key=key)
    data = http_get_json(url)
    rows = dig(data, "response.data")
    series: dict[str, float] = {}
    for row in rows:
        period = str(row["period"])  # e.g. 2024-03
        date = f"{period}-01" if len(period) == 7 else period
        # EIA retail price is cents/kWh
        series[date] = float(row["price"]) / 100.0
    write_cache(data_dir, "electricity_usd_per_kwh", series, url.replace(key, "<key>"))
    return f"electricity: {len(series)} monthly points"


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch and cache claim data")
    parser.add_argument("--config", default="research.yaml")
    parser.add_argument("--force", action="store_true", help="Refetch even when cached")
    args = parser.parse_args()
    config = load_research_config(args.config)
    data_dir = Path(config.get("data_dir", "data"))

    jobs = [
        ("qi_usd", lambda: fetch_price(config, data_dir, "qi_usd", "qi_url")),
        ("btc_usd", lambda: fetch_price(config, data_dir, "btc_usd", "btc_url")),
        ("difficulty", lambda: fetch_difficulty(config, data_dir)),
        ("electricity_usd_per_kwh", lambda: fetch_electricity(config, data_dir)),
    ]
    failures = 0
    for name, job in jobs:
        if not args.force and name != "difficulty" and read_cache(data_dir, name):
            print(f"{name}: cached (use --force to refetch)")
            continue
        try:
            print(job())
        except Exception as exc:
            failures += 1
            print(f"{name}: FETCH FAILED ({type(exc).__name__}: {exc}); existing cache untouched")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
