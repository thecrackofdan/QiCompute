from __future__ import annotations

import hashlib
import secrets
from typing import Any
from uuid import uuid4

from db import WorkerDB
from receipts import utc_now_iso


PENDING = "pending"
ACTIVE = "active"
REVOKED = "revoked"


def create_worker_enrollment(db: WorkerDB, worker_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    enrollment = {
        "worker_id": worker_id,
        "enrollment_id": str(uuid4()),
        "shared_secret_hash": None,
        "status": PENDING,
        "created_at": utc_now_iso(),
        "activated_at": None,
        "revoked_at": None,
        "metadata": metadata or {},
    }
    db.create_worker_enrollment(enrollment)
    return enrollment


def activate_worker_enrollment(db: WorkerDB, worker_id: str, shared_secret: str) -> dict[str, Any]:
    current = db.get_worker_enrollment(worker_id) or create_worker_enrollment(db, worker_id)
    enrollment = {
        **current,
        "shared_secret_hash": hash_shared_secret(shared_secret),
        "status": ACTIVE,
        "activated_at": utc_now_iso(),
        "revoked_at": None,
    }
    db.create_worker_enrollment(enrollment)
    return enrollment


def revoke_worker_enrollment(db: WorkerDB, worker_id: str) -> dict[str, Any] | None:
    current = db.get_worker_enrollment(worker_id)
    if not current:
        return None
    enrollment = {**current, "status": REVOKED, "revoked_at": utc_now_iso()}
    db.create_worker_enrollment(enrollment)
    return enrollment


def get_active_worker_secret(db: WorkerDB, worker_id: str, candidate_secret: str) -> str | None:
    enrollment = db.get_worker_enrollment(worker_id)
    if not enrollment or enrollment["status"] != ACTIVE:
        return None
    expected = enrollment.get("shared_secret_hash")
    if expected and secrets.compare_digest(expected, hash_shared_secret(candidate_secret)):
        return candidate_secret
    return None


def hash_shared_secret(shared_secret: str) -> str:
    return hashlib.sha256(shared_secret.encode("utf-8")).hexdigest()
