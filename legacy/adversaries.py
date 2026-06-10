from __future__ import annotations

import random
from dataclasses import dataclass, asdict
from typing import Any

import failures


MALICIOUS_WORKER = "malicious_worker"
MALICIOUS_CUSTOMER = "malicious_customer"
MALICIOUS_VERIFIER = "malicious_verifier"
SPAMMER = "spammer"
ESCROW_GRIEFER = "escrow_griefer"
REPLAY_ATTACKER = "replay_attacker"
COLLUDING_COMMITTEE = "colluding_committee"


@dataclass(frozen=True)
class AdversaryProfile:
    profile_id: str
    attack_behavior: str
    attack_frequency: float
    expected_failure_patterns: list[str]
    reputation_effects: dict[str, Any]
    settlement_effects: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def adversary_profiles(seed: int | None = None) -> dict[str, dict[str, Any]]:
    rng = random.Random(seed)
    profiles = [
        AdversaryProfile(MALICIOUS_WORKER, "submits malformed or tampered receipts", 0.35, [failures.VERIFICATION_FAILED, failures.CHALLENGE_FAILED], {"worker": "decrease"}, {"payout": "blocked"}),
        AdversaryProfile(MALICIOUS_CUSTOMER, "underfunds jobs or disputes results", 0.25, [failures.ESCROW_UNDERFUNDED], {"customer": "placeholder-negative"}, {"escrow": "rejected_or_refunded"}),
        AdversaryProfile(MALICIOUS_VERIFIER, "casts coordinated false committee votes", 0.30, [failures.COMMITTEE_DISPUTED], {"verifier": "suspicious"}, {"settlement": "disputed"}),
        AdversaryProfile(SPAMMER, "floods job or receipt submission paths", 0.80, [failures.RATE_LIMITED], {"actor": "rate_limited"}, {"settlement": "none"}),
        AdversaryProfile(ESCROW_GRIEFER, "locks capacity with excessive outstanding escrow", 0.50, [failures.ESCROW_LIMIT_EXCEEDED], {"customer": "placeholder-negative"}, {"escrow": "blocked_or_expired"}),
        AdversaryProfile(REPLAY_ATTACKER, "replays receipts or invoices", 0.45, [failures.DUPLICATE_RECEIPT, failures.STALE_RECEIPT], {"actor": "audit_event"}, {"payout": "idempotent"}),
        AdversaryProfile(COLLUDING_COMMITTEE, "clusters malicious verifiers into repeated committees", 0.40, [failures.COMMITTEE_DISPUTED], {"verifier_cluster": "suspicious"}, {"settlement": "blocked"}),
    ]
    rng.shuffle(profiles)
    return {profile.profile_id: profile.to_dict() for profile in profiles}
