from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from invoices import build_settlement_invoice, compute_invoice_hash
from load_test import run_load_test


def deterministic_seed(seed: int = 42) -> int:
    return int(seed)


def compare_simulation_runs(seed: int = 42) -> dict[str, Any]:
    first = _stress_digest(seed)
    second = _stress_digest(seed)
    different = _stress_digest(seed + 1)
    return {
        "same_seed_equal": first == second,
        "different_seed_differs": first != different,
        "first": first,
        "second": second,
        "different": different,
    }


def compare_epoch_outputs(seed: int = 42) -> dict[str, Any]:
    first = _load_digest(seed)
    second = _load_digest(seed)
    return {"same_seed_equal": first == second, "first": first, "second": second}


def compare_invoice_outputs() -> dict[str, Any]:
    job = {"job_id": "deterministic-job", "customer_id": "customer-a", "assigned_worker_id": "worker-a", "updated_at": "2026-01-01T00:00:00+00:00"}
    epoch = {"epoch_id": "epoch-a", "ended_at": "2026-01-01T00:01:00+00:00"}
    receipt = {"worker_id": "worker-a", "receipt_hash": "abc123", "estimated_qi_owed": 0.1, "ended_at": "2026-01-01T00:01:00+00:00"}
    escrow = {"settled_qi": 0.1, "fee_qi": 0.0025, "worker_payout_qi": 0.0975, "refunded_qi": 0.0, "status": "settled"}
    first = build_settlement_invoice(invoice_type="customer", job=job, epoch=epoch, receipt=receipt, escrow=escrow)
    second = build_settlement_invoice(invoice_type="customer", job=job, epoch=epoch, receipt=receipt, escrow=escrow)
    return {"same_invoice_equal": first == second, "invoice_hash": compute_invoice_hash(first)}


def run_determinism_checks(seed: int = 42) -> dict[str, Any]:
    simulation = compare_simulation_runs(seed)
    epochs = compare_epoch_outputs(seed)
    invoices = compare_invoice_outputs()
    accepted = simulation["same_seed_equal"] and epochs["same_seed_equal"] and invoices["same_invoice_equal"]
    return {"accepted": accepted, "simulation": simulation, "epochs": epochs, "invoices": invoices}


def main() -> int:
    parser = argparse.ArgumentParser(description="Check deterministic QiCompute simulation outputs")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    result = run_determinism_checks(args.seed)
    print("QiCompute Determinism Report")
    print(f"status: {'PASS' if result['accepted'] else 'FAIL'}")
    print(f"simulation_same_seed_equal: {result['simulation']['same_seed_equal']}")
    print(f"simulation_different_seed_differs: {result['simulation']['different_seed_differs']}")
    print(f"epoch_same_seed_equal: {result['epochs']['same_seed_equal']}")
    print(f"invoice_same_seed_equal: {result['invoices']['same_invoice_equal']}")
    return 0 if result["accepted"] else 1


def _stress_digest(seed: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        result = run_load_test(workers=2 + seed % 2, jobs=5 + seed % 3, seed=seed, db_path=str(Path(tmp) / "determinism-load.db"))
    digest = _stable_subset(result, ("workers", "jobs_submitted", "jobs_completed", "jobs_failed", "jobs_refunded", "total_settled_qi", "total_refunded_qi"))
    digest["seed"] = seed
    return digest


def _load_digest(seed: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        result = run_load_test(workers=3, jobs=6, seed=seed, db_path=str(Path(tmp) / "load.db"))
    return _stable_subset(result, ("jobs_submitted", "jobs_completed", "jobs_failed", "jobs_refunded", "total_settled_qi", "total_refunded_qi"))


def _stable_subset(result: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    stable = {key: result.get(key) for key in keys}
    return json.loads(json.dumps(stable, sort_keys=True, default=str))


if __name__ == "__main__":
    raise SystemExit(main())
