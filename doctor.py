from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worker import load_config


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    message: str


def run_checks(config_path: str = "config.yaml") -> list[CheckResult]:
    results: list[CheckResult] = []
    results.append(
        CheckResult(
            "python",
            "PASS" if sys.version_info >= (3, 10) else "FAIL",
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
    )
    results.append(CheckResult("sqlite", "PASS", sqlite3.sqlite_version))

    try:
        config = load_config(config_path)
        results.append(CheckResult("config", "PASS", config_path))
    except Exception as exc:
        return [*results, CheckResult("config", "FAIL", str(exc))]

    runtime_cfg = config.get("runtime", {})
    runtime_type = runtime_cfg.get("type", "simulated")
    valid_runtimes = {"simulated", "subprocess", "ollama", "ollama_placeholder", "llama_cpp_placeholder"}
    results.append(
        CheckResult(
            "runtime_config",
            "PASS" if runtime_type in valid_runtimes else "FAIL",
            f"type={runtime_type}",
        )
    )

    db_path = Path(config.get("worker", {}).get("db_path", "worker.db"))
    db_dir = db_path.parent if str(db_path.parent) else Path(".")
    results.append(
        CheckResult(
            "db_path",
            "PASS" if os.access(db_dir, os.W_OK) else "FAIL",
            str(db_path),
        )
    )

    for dirname in ("jobs", "jobs_done", "jobs_failed"):
        path = Path(dirname)
        status = "PASS" if path.exists() else "WARN"
        results.append(CheckResult(f"directory:{dirname}", status, "exists" if path.exists() else "will be created when needed"))

    if runtime_type == "ollama" or runtime_cfg.get("ollama_url"):
        results.append(_check_ollama(runtime_cfg.get("ollama_url", "http://127.0.0.1:11434/api/generate")))
        results.append(CheckResult("ollama_model", "WARN", f"configured={runtime_cfg.get('ollama_model', 'unset')} availability not checked"))
    else:
        results.append(CheckResult("ollama", "WARN", "not configured for active runtime"))

    return results


def print_results(results: list[CheckResult]) -> None:
    counts = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
        print(f"{result.status:4} {result.name}: {result.message}")
    print(f"Summary: PASS={counts['PASS']} WARN={counts['WARN']} FAIL={counts['FAIL']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate local QiCompute development/runtime environment")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    print_results(run_checks(args.config))
    return 0


def _check_ollama(url: str) -> CheckResult:
    request = urllib.request.Request(url, method="POST", data=b'{"model":"doctor","prompt":"","stream":false}')
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=1) as response:
            return CheckResult("ollama", "PASS", f"reachable status={getattr(response, 'status', 'ok')}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return CheckResult("ollama", "WARN", f"not reachable at {url}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
