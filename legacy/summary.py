from __future__ import annotations

from typing import Any


def print_epoch_summary(epoch: dict[str, Any]) -> None:
    metadata = epoch.get("metadata", {})
    print("Settlement Epoch")
    print(f"  epoch_id: {epoch.get('epoch_id')}")
    print(f"  verified jobs: {epoch.get('total_verified_jobs', 0)}")
    print(f"  rejected jobs: {metadata.get('rejected_jobs', epoch.get('total_failed_jobs', 0))}")
    print(f"  disputed jobs: {metadata.get('disputed_committee_count', 0)}")
    print(f"  total settled Qi: {epoch.get('total_settled_qi', 0):.12f}")
    print(f"  total rejected Qi: {metadata.get('total_rejected_qi', 0):.12f}")
    print(f"  total energy joules: {epoch.get('total_energy_joules', 0):.6f}")
    print(f"  total tokens: {epoch.get('total_tokens', 0):.6f}")
    print(f"  average tokens/sec: {metadata.get('average_tokens_per_second', 0):.6f}")


def print_worker_summary(worker: dict[str, Any]) -> None:
    print("Worker")
    print(f"  worker_id: {worker.get('worker_id')}")
    print(f"  reputation: {worker.get('reputation_score', 0):.2f}")
    print(f"  completed jobs: {worker.get('success_count', 0)}")
    print(f"  failed jobs: {worker.get('failure_count', 0)}")
    print(f"  committee outcomes: {worker.get('metadata', {}).get('committee_outcomes', {})}")
    print(f"  average latency ms: {worker.get('average_latency_ms', 0):.6f}")
    print(f"  energy efficiency J/token: {worker.get('average_energy_per_token', 0):.6f}")


def print_job_summary(job: dict[str, Any]) -> None:
    metadata = job.get("metadata", {})
    print("Job")
    print(f"  job_id: {job.get('job_id')}")
    print(f"  routed worker: {job.get('assigned_worker_id')}")
    print(f"  status: {job.get('status')}")
    print(f"  runtime type: {metadata.get('runtime_type')}")
    print(f"  verification outcome: {metadata.get('verification_outcome')}")
    print(f"  challenge outcome: {metadata.get('challenge_outcome')}")
    print(f"  committee outcome: {metadata.get('committee_outcome')}")
    print(f"  payout eligibility: {metadata.get('payout_eligible', False)}")


def print_committee_summary(committee: dict[str, Any]) -> None:
    if not committee:
        print("Committee")
        print("  result: not run")
        return
    print("Committee")
    print(f"  committee_id: {committee.get('committee_id')}")
    print(f"  result: {committee.get('result')}")
    print(f"  verifiers: {','.join(committee.get('verifier_worker_ids', []))}")
    print(f"  quorum: {committee.get('quorum_threshold')}")
    print(f"  vote counts: {committee.get('metadata', {}).get('vote_counts', {})}")
