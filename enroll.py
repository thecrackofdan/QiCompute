from __future__ import annotations

import argparse
import secrets
from pathlib import Path
from typing import Any

from db import WorkerDB
from enrollment import activate_worker_enrollment, create_worker_enrollment, revoke_worker_enrollment
from worker import load_config


def create_worker(db: WorkerDB, worker_id: str) -> dict[str, Any]:
    return create_worker_enrollment(db, worker_id)


def activate_worker(db: WorkerDB, worker_id: str, shared_secret: str | None = None) -> tuple[dict[str, Any], str]:
    secret = shared_secret or secrets.token_urlsafe(32)
    enrollment = activate_worker_enrollment(db, worker_id, secret)
    return enrollment, secret


def revoke_worker(db: WorkerDB, worker_id: str) -> dict[str, Any] | None:
    return revoke_worker_enrollment(db, worker_id)


def config_snippet(worker_id: str, shared_secret: str, controller_url: str) -> str:
    return (
        "worker:\n"
        f"  id: \"{worker_id}\"\n"
        "cluster:\n"
        "  enabled: true\n"
        "  node_role: \"worker\"\n"
        f"  controller_url: \"{controller_url}\"\n"
        f"  shared_secret: \"{shared_secret}\"\n"
    )


def write_worker_config(path: str, worker_id: str, shared_secret: str, controller_url: str) -> None:
    Path(path).write_text(config_snippet(worker_id, shared_secret, controller_url), encoding="utf-8")


def list_workers(db: WorkerDB) -> list[dict[str, Any]]:
    rows = db.conn.execute("SELECT worker_id, enrollment_id, status, created_at, activated_at, revoked_at FROM worker_enrollments ORDER BY worker_id")
    return [dict(row) for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description="Enroll QiCompute LAN workers")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--create-worker")
    parser.add_argument("--activate-worker")
    parser.add_argument("--revoke-worker")
    parser.add_argument("--list-workers", action="store_true")
    parser.add_argument("--write-config")
    parser.add_argument("--print-config", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    db = WorkerDB(config["worker"]["db_path"])
    try:
        if args.create_worker:
            enrollment = create_worker(db, args.create_worker)
            print(f"worker_id={enrollment['worker_id']}")
            print(f"status={enrollment['status']}")
            return 0
        if args.activate_worker:
            enrollment, secret = activate_worker(db, args.activate_worker)
            print(f"worker_id={enrollment['worker_id']}")
            print(f"status={enrollment['status']}")
            print(f"shared_secret={secret}")
            controller_url = config.get("cluster", {}).get("controller_url", "http://127.0.0.1:8080")
            if args.print_config:
                print(config_snippet(args.activate_worker, secret, controller_url))
            if args.write_config:
                write_worker_config(args.write_config, args.activate_worker, secret, controller_url)
            return 0
        if args.revoke_worker:
            enrollment = revoke_worker(db, args.revoke_worker)
            print(f"worker_id={args.revoke_worker}")
            print(f"status={enrollment['status'] if enrollment else 'missing'}")
            return 0
        if args.list_workers:
            for worker in list_workers(db):
                print(f"{worker['worker_id']} status={worker['status']} enrollment_id={worker['enrollment_id']}")
            return 0
        parser.print_help()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
