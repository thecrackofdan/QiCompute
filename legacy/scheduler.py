from __future__ import annotations

import json
import shutil
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from shutil import which
from typing import Any
from uuid import uuid4

import failures
from challenges import (
    build_challenge_result,
    create_challenge,
    should_attach_challenge,
    verify_challenge_result,
)
from committees import ACCEPTED, create_verification_committee, run_verification_committee
from db import WorkerDB
from epochs import active_epoch
from receipts import compute_receipt_hash, make_receipt, utc_now_iso
from reputation import update_worker_reputation
from telemetry import GPUTelemetry
from verifier import VerificationResult, verify_inference_receipt


class Scheduler:
    def __init__(self, config: dict[str, Any], db: WorkerDB, telemetry: GPUTelemetry):
        self.config = config
        self.db = db
        self.telemetry = telemetry
        self.worker_id = config["worker"]["id"]
        self.jobs_dir = Path(config["jobs"]["queue_dir"])
        self.completed_dir = Path(config["jobs"]["completed_dir"])
        self.failed_dir = Path(config["jobs"]["failed_dir"])
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.completed_dir.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)

    def run_forever(self) -> None:
        interval = float(self.config["worker"].get("loop_interval_seconds", 5))
        while True:
            receipt = self.run_once()
            print_receipt(receipt, self.db.get_balance(self.worker_id))
            time.sleep(interval)

    def run_once(self) -> dict[str, Any]:
        self._log_telemetry()
        job_path = self._next_job()
        if job_path and self.config["inference"].get("enabled", True):
            return self._run_inference(job_path)
        if not self.config["mining"].get("enabled", True):
            raise RuntimeError("No inference job can run and mining is disabled")
        return self._run_mining()

    def _next_job(self) -> Path | None:
        jobs = sorted(self.jobs_dir.glob("*.json"))
        return jobs[0] if jobs else None

    def _run_inference(self, job_path: Path) -> dict[str, Any]:
        inference_cfg = self.config["inference"]
        started = utc_now_iso()
        start_time = time.monotonic()
        start_watts = self.telemetry.total_watts()
        metadata: dict[str, Any] = {"job_file": str(job_path)}
        job: dict[str, Any] = {}

        try:
            job = json.loads(job_path.read_text(encoding="utf-8"))
            metadata["job"] = job
            metadata["job_id"] = job.get("id")
            command = job.get("command") or inference_cfg.get("command") or ""
            if command:
                self._run_command(command, timeout=float(job.get("timeout_seconds", 300)))
            else:
                time.sleep(float(job.get("seconds", inference_cfg.get("seconds_per_job", 3))))
            input_tokens = float(job.get("input_tokens", 0))
            output_tokens = float(job.get("output_tokens", job.get("tokens", inference_cfg.get("default_tokens", 256))))
            tokens = output_tokens
            accepted = bool(job.get("accepted", True))
            shutil.move(str(job_path), self.completed_dir / job_path.name)
        except Exception as exc:
            metadata["error"] = str(exc)
            metadata["failure_code"] = failures.COMMAND_FAILED
            shutil.move(str(job_path), self.failed_dir / job_path.name)
            input_tokens = 0.0
            output_tokens = 0.0
            tokens = 0.0
            accepted = False

        metadata["accepted"] = accepted
        metadata["input_tokens"] = input_tokens
        metadata["output_tokens"] = output_tokens
        metadata["worker"] = self._worker_metadata()
        challenge = None
        if accepted and job and should_attach_challenge(job, self.config):
            challenge = create_challenge(job, self.worker_id, self.config)
            self.db.insert_challenge(challenge)
            metadata["challenge_id"] = challenge["challenge_id"]
            metadata["challenge_response_hash"] = job.get(
                "challenge_response_hash",
                challenge["expected_hash"],
            )
        estimated_qi = self._inference_payout(input_tokens, output_tokens, accepted)
        job_id = job.get("id")
        duplicate_job = bool(job_id and self.db.inference_job_was_paid(str(job_id)))
        if duplicate_job:
            metadata["duplicate_job"] = True
            metadata["failure_code"] = failures.DUPLICATE_JOB

        receipt = self._build_receipt(
            mode="inference",
            started_at=started,
            start_time=start_time,
            start_watts=start_watts,
            output_type="tokens",
            output_amount=tokens,
            estimated_qi=estimated_qi,
            metadata=metadata,
        )
        verification = verify_inference_receipt(receipt, job, self.config)
        challenge_result = None
        if challenge:
            challenge_verification = verify_challenge_result(challenge, receipt)
            challenge_result = build_challenge_result(challenge, receipt, challenge_verification)
            self.db.record_challenge_result(challenge_result)
            receipt["metadata"]["challenge_verification"] = challenge_verification.to_dict()
            if not challenge_verification.accepted:
                verification = VerificationResult(
                    accepted=False,
                    reason=challenge_verification.reason,
                    score=0.0,
                    metadata={
                        "job_id": job.get("id"),
                        "worker_id": receipt.get("worker_id"),
                        "challenge": challenge_verification.to_dict(),
                        "payout_eligible": False,
                    },
                )
        if verification.accepted and self.config.get("committees", {}).get("enabled", False):
            receipt["receipt_hash"] = self._refresh_receipt_hash(receipt)
            committee_cfg = self.config.get("committees", {})
            epoch = active_epoch(self.db)
            committee = create_verification_committee(
                self.db,
                challenge_id=challenge["challenge_id"] if challenge else None,
                assigned_worker_id=self.worker_id,
                committee_size=int(committee_cfg.get("committee_size", 3)),
                quorum_threshold=int(committee_cfg.get("quorum_threshold", 2)),
                metadata={"job_id": job.get("id"), "epoch_id": epoch["epoch_id"]},
            )
            committee_result = run_verification_committee(
                self.db,
                committee,
                receipt=receipt,
                challenge_result=challenge_result,
                forced_votes=committee_cfg.get("forced_votes"),
            )
            receipt["metadata"]["committee_verification"] = {
                "committee_id": committee_result["committee_id"],
                "result": committee_result["result"],
                "vote_counts": committee_result["metadata"].get("vote_counts", {}),
            }
            if committee_result["result"] != ACCEPTED:
                verification = VerificationResult(
                    accepted=False,
                    reason=failures.COMMITTEE_REJECTED
                    if committee_result["result"] == "rejected"
                    else failures.COMMITTEE_DISPUTED,
                    score=0.0,
                    metadata={
                        "job_id": job.get("id"),
                        "worker_id": receipt.get("worker_id"),
                        "committee": receipt["metadata"]["committee_verification"],
                        "payout_eligible": False,
                    },
                )
        receipt["metadata"]["verification"] = verification.to_dict()
        receipt["receipt_hash"] = self._refresh_receipt_hash(receipt)
        self.db.insert_receipt(receipt)
        if verification.accepted and estimated_qi > 0 and job_id and not duplicate_job:
            event = self._payout_event(
                event_type="inference_job",
                basis="verified_accepted_tokens",
                qi_amount=estimated_qi,
                source_id=receipt["receipt_id"],
                metadata={
                    "job_id": job_id,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "job_file": str(job_path),
                    "verification_score": verification.score,
                    "verification_reason": verification.reason,
                },
                epoch_id=active_epoch(self.db)["epoch_id"],
            )
            self.db.insert_payout_event(event)
            self.db.record_inference_job_paid(
                job_id=str(job_id),
                worker_id=self.worker_id,
                receipt_id=receipt["receipt_id"],
                accepted_at=event["created_at"],
                payout_event_id=event["event_id"],
            )
        update_worker_reputation(
            self.db,
            worker_id=self.worker_id,
            verification=verification.to_dict(),
            receipt=receipt,
            duplicate_job=duplicate_job,
        )
        return receipt

    def _run_mining(self) -> dict[str, Any]:
        mining_cfg = self.config["mining"]
        started = utc_now_iso()
        start_time = time.monotonic()
        start_watts = self.telemetry.total_watts()
        command = mining_cfg.get("command") or ""
        cycle_seconds = float(mining_cfg.get("cycle_seconds", 15))

        metadata = {"launcher": "placeholder", "command": command}
        command_failed = False
        try:
            if command:
                self._run_command(command, timeout=cycle_seconds)
            else:
                time.sleep(cycle_seconds)
        except Exception as exc:
            command_failed = True
            metadata["error"] = str(exc)
            metadata["failure_code"] = failures.COMMAND_FAILED

        duration = time.monotonic() - start_time
        shares = 0.0 if command_failed else duration * float(mining_cfg.get("estimated_shares_per_second", 0))
        share_difficulty = float(mining_cfg.get("share_difficulty", 1))
        receipt = self._build_receipt(
            mode="mining",
            started_at=started,
            start_time=start_time,
            start_watts=start_watts,
            output_type="shares",
            output_amount=shares,
            estimated_qi=0.0,
            metadata=metadata,
        )
        self.db.insert_receipt(receipt)
        self._record_mining_shares(receipt, shares, share_difficulty, accepted=not command_failed)
        return receipt

    def distribute_block_reward(self, block_hash: str, reward_qi: float) -> dict[str, Any]:
        if not block_hash:
            raise ValueError("block_hash is required")
        if reward_qi <= 0:
            raise ValueError("reward_qi must be positive")
        if self.db.mining_round_for_block_hash(block_hash):
            raise ValueError(f"block_hash has already been settled: {block_hash}")
        mining_cfg = self.config["mining"]
        pool_fee_percent = float(mining_cfg.get("pool_fee_percent", 0))
        pplns_window_weight = float(
            mining_cfg.get("pplns_window_weight", mining_cfg.get("pplns_window_shares", 1000))
        )
        if pool_fee_percent < 0 or pool_fee_percent >= 100:
            raise ValueError("pool_fee_percent must be between 0 and 100")
        if pplns_window_weight <= 0:
            raise ValueError("pplns_window_weight must be positive")
        shares = self.db.accepted_shares_for_pplns(pplns_window_weight)
        if not shares:
            raise RuntimeError("Cannot distribute block reward without accepted mining shares")

        round_id = str(uuid4())
        started_at = shares[-1]["submitted_at"]
        ended_at = utc_now_iso()
        pool_fee_qi = reward_qi * pool_fee_percent / 100
        net_reward_qi = reward_qi - pool_fee_qi
        weights: dict[str, float] = defaultdict(float)
        for share in shares:
            weights[share["worker_id"]] += float(share["difficulty"])
        total_weight = sum(weights.values())
        if total_weight <= 0:
            raise RuntimeError("Cannot distribute block reward without positive share weight")

        self.db.insert_mining_round(
            {
                "round_id": round_id,
                "block_hash": block_hash,
                "started_at": started_at,
                "ended_at": ended_at,
                "reward_qi": reward_qi,
                "pool_fee_qi": pool_fee_qi,
                "net_reward_qi": net_reward_qi,
                "policy": f"PPLNS_WEIGHT:{pplns_window_weight}",
                "metadata": {"eligible_shares": len(shares), "target_weight": pplns_window_weight, "total_weight": total_weight},
            }
        )
        self.db.assign_mining_shares_to_round([share["share_id"] for share in shares], round_id)
        payouts = []
        for worker_id, weight in weights.items():
            qi_amount = net_reward_qi * weight / total_weight
            event = self._payout_event(
                event_type="mining_block_reward",
                basis="pplns",
                qi_amount=qi_amount,
                source_id=round_id,
                metadata={
                    "block_hash": block_hash,
                    "round_id": round_id,
                    "worker_share_weight": weight,
                    "total_share_weight": total_weight,
                    "pool_fee_percent": pool_fee_percent,
                },
                worker_id=worker_id,
                epoch_id=active_epoch(self.db)["epoch_id"],
            )
            self.db.insert_payout_event(event)
            payouts.append(event)

        return {
            "round_id": round_id,
            "block_hash": block_hash,
            "reward_qi": reward_qi,
            "net_reward_qi": net_reward_qi,
            "eligible_shares": len(shares),
            "eligible_share_weight": total_weight,
            "payouts": payouts,
        }

    def _build_receipt(
        self,
        *,
        mode: str,
        started_at: str,
        start_time: float,
        start_watts: float,
        output_type: str,
        output_amount: float,
        estimated_qi: float,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        ended_at = utc_now_iso()
        duration = time.monotonic() - start_time
        end_watts = self.telemetry.total_watts()
        average_watts = (start_watts + end_watts) / 2
        receipt = make_receipt(
            worker_id=self.worker_id,
            mode=mode,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration,
            average_watts=average_watts,
            output_type=output_type,
            output_amount=output_amount,
            estimated_qi_owed=estimated_qi,
            metadata=metadata,
        ).to_dict()
        return receipt

    def _inference_payout(self, input_tokens: float, output_tokens: float, accepted: bool) -> float:
        if not accepted:
            return 0.0
        inference_cfg = self.config["inference"]
        fallback_rate = float(inference_cfg.get("estimated_qi_per_token", 0))
        input_rate = float(inference_cfg.get("estimated_qi_per_input_token", fallback_rate))
        output_rate = float(inference_cfg.get("estimated_qi_per_output_token", fallback_rate))
        return input_tokens * input_rate + output_tokens * output_rate

    def _record_mining_shares(
        self,
        receipt: dict[str, Any],
        shares: float,
        share_difficulty: float,
        *,
        accepted: bool,
    ) -> None:
        whole_shares = int(shares)
        fractional_share = shares - whole_shares
        share_count = whole_shares + (1 if fractional_share > 0 else 0)
        for index in range(share_count):
            difficulty = fractional_share if index == whole_shares and fractional_share > 0 else 1.0
            self.db.insert_mining_share(
                {
                    "share_id": str(uuid4()),
                    "worker_id": self.worker_id,
                    "submitted_at": receipt["ended_at"],
                    "difficulty": difficulty * share_difficulty,
                    "accepted": accepted and difficulty > 0,
                    "stale": False,
                    "receipt_id": receipt["receipt_id"],
                    "metadata": {"mode": "placeholder", "receipt_output_shares": shares},
                }
            )

    def _payout_event(
        self,
        *,
        event_type: str,
        basis: str,
        qi_amount: float,
        source_id: str,
        metadata: dict[str, Any],
        worker_id: str | None = None,
        epoch_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "event_id": str(uuid4()),
            "worker_id": worker_id or self.worker_id,
            "event_type": event_type,
            "basis": basis,
            "qi_amount": round(qi_amount, 12),
            "created_at": utc_now_iso(),
            "source_id": source_id,
            "epoch_id": epoch_id,
            "metadata": metadata,
        }

    def _worker_metadata(self) -> dict[str, Any]:
        worker_cfg = self.config.get("worker", {})
        return {
            "id": worker_cfg.get("id"),
            "operator": worker_cfg.get("operator"),
            "public_key": worker_cfg.get("public_key"),
            "region": worker_cfg.get("region"),
            "hardware_profile": worker_cfg.get(
                "hardware_profile",
                {
                    "gpu_count": None,
                    "gpu_names": [],
                    "total_vram_gb": None,
                    "fallback_watts": worker_cfg.get("fallback_watts"),
                },
            ),
        }

    def _refresh_receipt_hash(self, receipt: dict[str, Any]) -> str:
        receipt.pop("receipt_hash", None)
        return compute_receipt_hash(receipt)

    def _log_telemetry(self) -> None:
        for sample in self.telemetry.sample():
            self.db.insert_telemetry(sample)

    def _run_command(self, command: Any, timeout: float) -> None:
        args = self._validated_command(command)
        subprocess.run(args, check=True, timeout=timeout)

    def _validated_command(self, command: Any) -> list[str]:
        if isinstance(command, str):
            raise ValueError("Commands must be configured as an argument list, not a shell string")
        if not isinstance(command, list) or not command:
            raise ValueError("Command must be a non-empty argument list")
        if not isinstance(command[0], str) or not command[0]:
            raise ValueError("Command executable must be a non-empty string")
        if not all(isinstance(part, str) for part in command):
            raise ValueError("Command arguments must be strings")

        executable = command[0]
        if "/" in executable:
            executable_path = Path(executable)
            if not executable_path.is_file():
                raise ValueError(f"Command executable does not exist: {executable}")
            if not executable_path.stat().st_mode & 0o111:
                raise ValueError(f"Command executable is not executable: {executable}")
        elif which(executable) is None:
            raise ValueError(f"Command executable not found on PATH: {executable}")
        return command


def print_receipt(receipt: dict[str, Any], balance: float) -> None:
    output = receipt["output"]
    print(
        f"{receipt['ended_at']} mode={receipt['mode']} "
        f"energy_j={receipt['energy_joules']:.2f} "
        f"{output['type']}={output['amount']:.4f} "
        f"estimated_qi={receipt['estimated_qi_owed']:.12f} "
        f"settled_balance={balance:.12f}"
    )
