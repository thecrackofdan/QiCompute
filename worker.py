from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

from db import WorkerDB
from scheduler import Scheduler, print_receipt
from telemetry import GPUTelemetry


def main() -> None:
    parser = argparse.ArgumentParser(description="Unified Qi compute/mining pool worker")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--once", action="store_true", help="Run one scheduler cycle and exit")
    parser.add_argument("--balance", action="store_true", help="Print local estimated Qi balance and exit")
    parser.add_argument("--recent", type=int, default=0, help="Print recent receipts and exit")
    parser.add_argument("--payouts", type=int, default=0, help="Print recent payout events and exit")
    parser.add_argument("--settle-block-reward", type=float, default=0, help="Distribute a found block reward in Qi")
    parser.add_argument("--block-hash", default="prototype-block", help="Block hash/id for --settle-block-reward")
    args = parser.parse_args()

    config = load_config(args.config)
    db = WorkerDB(config["worker"]["db_path"])
    telemetry = GPUTelemetry(
        nvidia_smi_path=config["telemetry"].get("nvidia_smi_path", "nvidia-smi"),
        fallback_watts=float(config["worker"].get("fallback_watts", 250)),
    )

    try:
        worker_id = config["worker"]["id"]
        if args.balance:
            print(
                f"{worker_id} "
                f"settled_qi_balance={db.get_settled_balance(worker_id):.12f} "
                f"estimated_receipt_total={db.get_estimated_receipt_total(worker_id):.12f}"
            )
            return
        if args.recent:
            for row in db.recent_receipts(args.recent):
                print(dict(row))
            return
        if args.payouts:
            for row in db.recent_payout_events(args.payouts):
                print(dict(row))
            return

        scheduler = Scheduler(config, db, telemetry)
        if args.settle_block_reward:
            result = scheduler.distribute_block_reward(args.block_hash, args.settle_block_reward)
            print(
                f"round={result['round_id']} block={result['block_hash']} "
                f"eligible_shares={result['eligible_shares']} "
                f"net_reward_qi={result['net_reward_qi']:.12f}"
            )
            for event in result["payouts"]:
                print(
                    f"worker={event['worker_id']} "
                    f"qi_amount={event['qi_amount']:.12f} "
                    f"basis={event['basis']}"
                )
            return
        if args.once:
            receipt = scheduler.run_once()
            print_receipt(receipt, db.get_settled_balance(worker_id))
        else:
            scheduler.run_forever()
    finally:
        db.close()


def load_config(path: str) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except ModuleNotFoundError:
        return _minimal_yaml_load(text)


def _minimal_yaml_load(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    current_section: dict[str, Any] | None = None
    current_nested: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line:
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent == 0 and line.endswith(":"):
            key = line[:-1]
            result[key] = {}
            current_section = result[key]
            current_nested = None
            continue
        if current_section is None or ":" not in line:
            continue
        key, value = line.strip().split(":", 1)
        value = value.strip()
        if indent == 2 and value == "":
            current_section[key] = {}
            current_nested = current_section[key]
        elif indent >= 4 and current_nested is not None:
            current_nested[key] = _parse_scalar(value)
        else:
            current_section[key] = _parse_scalar(value)
            current_nested = None
    return result


def _parse_scalar(value: str) -> Any:
    if value in {"", '""', "''"}:
        return ""
    if value.lower() in {"null", "none"}:
        return None
    if value.startswith("[") and value.endswith("]"):
        parsed = ast.literal_eval(value)
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise ValueError("Only string lists are supported in fallback YAML parsing")
        return parsed
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.startswith(("'", '"')) and value.endswith(("'", '"')):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


if __name__ == "__main__":
    main()
