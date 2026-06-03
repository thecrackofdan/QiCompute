from __future__ import annotations

from collections import Counter
from typing import Any
from uuid import uuid4

import failures
from capabilities import make_capability_claim, verify_capability_claim
from db import WorkerDB
from receipts import utc_now_iso, verify_receipt_hash


ACCEPTED = "accepted"
REJECTED = "rejected"
DISPUTED = "disputed"


def select_verifier_workers(
    workers: list[dict[str, Any]],
    *,
    assigned_worker_id: str,
    committee_size: int,
) -> list[str]:
    eligible = [
        worker
        for worker in workers
        if worker.get("online") and worker.get("worker_id") != assigned_worker_id
    ]
    eligible.sort(key=lambda worker: (-float(worker.get("reputation_score", 50)), str(worker.get("worker_id"))))
    return [worker["worker_id"] for worker in eligible[:committee_size]]


def create_verification_committee(
    db: WorkerDB,
    *,
    challenge_id: str | None,
    assigned_worker_id: str,
    committee_size: int = 3,
    quorum_threshold: int = 2,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    verifier_ids = select_verifier_workers(
        db.list_online_workers(),
        assigned_worker_id=assigned_worker_id,
        committee_size=committee_size,
    )
    committee = {
        "committee_id": str(uuid4()),
        "challenge_id": challenge_id,
        "verifier_worker_ids": verifier_ids,
        "quorum_threshold": quorum_threshold,
        "created_at": utc_now_iso(),
        "finalized_at": None,
        "result": None,
        "metadata": metadata or {},
    }
    db.insert_verification_committee(committee)
    return committee


def run_verification_committee(
    db: WorkerDB,
    committee: dict[str, Any],
    *,
    receipt: dict[str, Any],
    challenge_result: dict[str, Any] | None,
    capability_claim: dict[str, Any] | None = None,
    forced_votes: dict[str, str] | None = None,
) -> dict[str, Any]:
    votes = []
    for verifier_id in committee.get("verifier_worker_ids", []):
        vote, reason = _verify_vote(
            db,
            verifier_id=verifier_id,
            receipt=receipt,
            challenge_result=challenge_result,
            capability_claim=capability_claim,
            forced_votes=forced_votes or {},
        )
        vote_data = {
            "vote_id": str(uuid4()),
            "committee_id": committee["committee_id"],
            "verifier_worker_id": verifier_id,
            "vote": vote,
            "reason": reason,
            "created_at": utc_now_iso(),
            "metadata": {
                "receipt_id": receipt.get("receipt_id"),
                "challenge_id": committee.get("challenge_id"),
            },
        }
        db.insert_committee_vote(vote_data)
        votes.append(vote_data)

    result = aggregate_committee_votes(votes, int(committee["quorum_threshold"]))
    quorum_not_reached = len(votes) < int(committee["quorum_threshold"])
    metadata = {
        **committee.get("metadata", {}),
        "vote_counts": dict(Counter(vote["vote"] for vote in votes)),
        "failure_code": failures.QUORUM_NOT_REACHED if quorum_not_reached else _failure_code_for_result(result),
    }
    finalized_at = utc_now_iso()
    db.finalize_verification_committee(committee["committee_id"], result, finalized_at, metadata)
    finalized = db.verification_committee(committee["committee_id"])
    finalized["votes"] = db.committee_votes(committee["committee_id"])
    return finalized


def aggregate_committee_votes(votes: list[dict[str, Any]], quorum_threshold: int) -> str:
    counts = Counter(vote["vote"] for vote in votes)
    if counts[ACCEPTED] >= quorum_threshold:
        return ACCEPTED
    if counts[REJECTED] >= quorum_threshold:
        return REJECTED
    return DISPUTED


def _verify_vote(
    db: WorkerDB,
    *,
    verifier_id: str,
    receipt: dict[str, Any],
    challenge_result: dict[str, Any] | None,
    capability_claim: dict[str, Any] | None,
    forced_votes: dict[str, str],
) -> tuple[str, str]:
    if verifier_id in forced_votes:
        vote = forced_votes[verifier_id]
        return vote, "forced local simulation vote"
    worker = db.get_worker(verifier_id)
    if worker and worker.get("metadata", {}).get("malicious_verifier_vote"):
        vote = worker["metadata"]["malicious_verifier_vote"]
        return vote, "malicious verifier simulation"
    if not verify_receipt_hash(receipt):
        return REJECTED, "receipt hash failed"
    if challenge_result and not challenge_result.get("accepted", False):
        return REJECTED, "challenge result failed"
    claim = capability_claim or (make_capability_claim(worker) if worker else None)
    if claim:
        capability = verify_capability_claim(claim)
        if not capability.get("accepted"):
            return REJECTED, capability.get("reason", failures.INVALID_CAPABILITY_CLAIM)
    return ACCEPTED, "committee verifier accepted"


def _failure_code_for_result(result: str) -> str | None:
    if result == REJECTED:
        return failures.COMMITTEE_REJECTED
    if result == DISPUTED:
        return failures.COMMITTEE_DISPUTED
    return None
