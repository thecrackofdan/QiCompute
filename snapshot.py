from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from db import WorkerDB
from epochs import active_epoch


def export_controller_snapshot(db: WorkerDB) -> dict[str, Any]:
    snapshot = {
        "workers": _workers(db),
        "active_jobs": _jobs(db),
        "active_epoch": active_epoch(db),
        "recent_cluster_events": db.recent_cluster_events(20),
        "routing_audit_logs": db.recent_routing_audit_logs(20),
        "outstanding_leases": _leases(db),
    }
    snapshot["snapshot_hash"] = compute_snapshot_hash(snapshot)
    return snapshot


def compute_snapshot_hash(snapshot: dict[str, Any]) -> str:
    payload = copy.deepcopy(snapshot)
    payload.pop("snapshot_hash", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _workers(db: WorkerDB) -> list[dict[str, Any]]:
    rows = db.conn.execute(
        """
        SELECT worker_id, region, online, reputation_score, success_count, failure_count,
               current_jobs, max_concurrent_jobs, load_percent
        FROM worker_registry
        ORDER BY worker_id ASC
        """
    )
    return [dict(row) for row in rows]


def _jobs(db: WorkerDB) -> list[dict[str, Any]]:
    rows = db.conn.execute(
        """
        SELECT job_id, customer_id, model, prompt_hash, status, assigned_worker_id,
               lease_id, lease_expires_at, assigned_at
        FROM customer_jobs
        WHERE status IN ('queued', 'retrying', 'routed', 'running')
        ORDER BY created_at ASC
        """
    )
    return [dict(row) for row in rows]


def _leases(db: WorkerDB) -> list[dict[str, Any]]:
    rows = db.conn.execute(
        """
        SELECT job_id, assigned_worker_id, lease_id, lease_expires_at, assigned_at
        FROM customer_jobs
        WHERE lease_id IS NOT NULL
        ORDER BY assigned_at ASC
        """
    )
    return [dict(row) for row in rows]
