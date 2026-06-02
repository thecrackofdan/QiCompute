from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

import failures
from capabilities import compute_capability_hash, make_capability_claim, verify_capability_claim
from customer_receipts import build_customer_receipt, compute_customer_receipt_hash
from db import WorkerDB
from envelopes import compute_envelope_hash, make_job_envelope, verify_job_envelope
from pricing import estimate_job_price
from registry import heartbeat_local_worker
from reputation import update_worker_reputation
from router import route_and_audit_inference_job, route_inference_job
from scheduler import Scheduler
from simulation import run_marketplace_simulation
from telemetry import GPUTelemetry
from receipts import make_receipt, utc_now_iso, verify_receipt_hash
from verifier import verify_inference_receipt
from worker import _minimal_yaml_load, load_config


class WorkerPrototypeTest(unittest.TestCase):
    def test_load_config_without_pyyaml_shape(self) -> None:
        config = load_config("config.yaml")

        self.assertEqual(config["worker"]["id"], "local-gpu-rig-001")
        self.assertIn("mining", config)
        self.assertIn("inference", config)
        self.assertEqual(config["mining"]["command"], [])
        self.assertIn("hardware_profile", config["worker"])

    def test_minimal_yaml_loader_supports_command_lists(self) -> None:
        config = _minimal_yaml_load(
            """
worker:
  id: "test"
  hardware_profile:
    gpu_count: null
    gpu_names: []
mining:
  command: ["python3", "miner.py"]
inference:
  command: []
"""
        )

        self.assertEqual(config["mining"]["command"], ["python3", "miner.py"])
        self.assertEqual(config["inference"]["command"], [])
        self.assertEqual(config["worker"]["hardware_profile"]["gpu_count"], None)
        self.assertEqual(config["worker"]["hardware_profile"]["gpu_names"], [])

    def test_telemetry_falls_back_when_nvidia_smi_missing(self) -> None:
        telemetry = GPUTelemetry(nvidia_smi_path="definitely-not-nvidia-smi", fallback_watts=123)

        samples = telemetry.sample()

        self.assertEqual(samples[0]["source"], "fallback")
        self.assertEqual(samples[0]["power_watts"], 123)

    def test_mines_when_no_job_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scheduler, db = self._scheduler(tmp)

            receipt = scheduler.run_once()
            payout_events = db.recent_payout_events(1)

            self.assertEqual(receipt["mode"], "mining")
            self.assertEqual(receipt["output"]["type"], "shares")
            self.assertGreater(receipt["energy_joules"], 0)
            self.assertEqual(db.get_balance("test-worker"), 0)
            self.assertEqual(payout_events, [])
            db.close()

    def test_db_rejects_mining_share_payout_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)

            with self.assertRaises(ValueError):
                db.insert_payout_event(
                    {
                        "event_id": str(uuid4()),
                        "worker_id": "test-worker",
                        "event_type": "mining_share",
                        "basis": "provisional_valid_share",
                        "qi_amount": 1,
                        "created_at": utc_now_iso(),
                        "source_id": "share-1",
                        "metadata": {},
                    }
                )
            self.assertEqual(db.get_balance("test-worker"), 0)
            db.close()

    def test_runs_inference_when_job_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs"
            job_dir.mkdir()
            (job_dir / "job.json").write_text(
                json.dumps({"id": "job-1", "tokens": 42, "seconds": 0.001}),
                encoding="utf-8",
            )
            scheduler, db = self._scheduler(tmp)

            receipt = scheduler.run_once()
            payout_events = db.recent_payout_events(1)

            self.assertEqual(receipt["mode"], "inference")
            self.assertEqual(receipt["output"]["amount"], 42)
            self.assertEqual(payout_events[0]["event_type"], "inference_job")
            self.assertFalse((job_dir / "job.json").exists())
            self.assertTrue((Path(tmp) / "done" / "job.json").exists())
            db.close()

    def test_valid_inference_receipt_verification(self) -> None:
        receipt = self._inference_receipt()
        job = {"id": "job-verify-1", "input_tokens": 10, "output_tokens": 20}

        result = verify_inference_receipt(receipt, job, self._config_for_verifier())

        self.assertTrue(result.accepted)
        self.assertEqual(result.score, 1.0)

    def test_rejected_inference_receipt_missing_job_id(self) -> None:
        receipt = self._inference_receipt()
        job: dict[str, object] = {"input_tokens": 10, "output_tokens": 20}

        result = verify_inference_receipt(receipt, job, self._config_for_verifier())

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, failures.VERIFICATION_FAILED)
        self.assertIn("job id is required", result.metadata["reason_detail"])

    def test_rejected_inference_receipt_negative_token_count(self) -> None:
        receipt = self._inference_receipt(input_tokens=-1)
        job = {"id": "job-negative", "input_tokens": -1, "output_tokens": 20}

        result = verify_inference_receipt(receipt, job, self._config_for_verifier())

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, failures.VERIFICATION_FAILED)
        self.assertIn("input token count must be non-negative", result.metadata["reason_detail"])

    def test_duplicate_inference_job_does_not_double_pay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs"
            job_dir.mkdir()
            job = {"id": "same-job", "input_tokens": 10, "output_tokens": 20, "seconds": 0.001}
            (job_dir / "a.json").write_text(json.dumps(job), encoding="utf-8")
            scheduler, db = self._scheduler(tmp)

            scheduler.run_once()
            first_balance = db.get_settled_balance("test-worker")
            (job_dir / "b.json").write_text(json.dumps(job), encoding="utf-8")
            scheduler.run_once()

            self.assertGreater(first_balance, 0)
            self.assertEqual(db.get_settled_balance("test-worker"), first_balance)
            self.assertGreater(db.get_estimated_receipt_total("test-worker"), first_balance)
            db.close()

    def test_receipt_hash_verifies_correctly(self) -> None:
        receipt = self._inference_receipt()

        self.assertTrue(verify_receipt_hash(receipt))

    def test_tampered_receipt_hash_fails(self) -> None:
        receipt = self._inference_receipt()
        receipt["output"]["amount"] = 999

        self.assertFalse(verify_receipt_hash(receipt))

    def test_estimated_receipt_total_is_separate_from_settled_balance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scheduler, db = self._scheduler(tmp)

            mining_receipt = scheduler.run_once()

            self.assertEqual(mining_receipt["mode"], "mining")
            self.assertEqual(db.get_settled_balance("test-worker"), 0)
            self.assertEqual(db.get_estimated_receipt_total("test-worker"), 0)

            job_dir = Path(tmp) / "jobs"
            job_dir.mkdir(exist_ok=True)
            (job_dir / "job.json").write_text(
                json.dumps({"id": "settled-job", "input_tokens": 1, "output_tokens": 2, "seconds": 0.001}),
                encoding="utf-8",
            )
            scheduler.run_once()

            self.assertEqual(db.get_settled_balance("test-worker"), db.get_estimated_receipt_total("test-worker"))
            db.close()

    def test_distributes_block_reward_over_recent_valid_shares(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scheduler, db = self._scheduler(tmp)
            scheduler.run_once()

            result = scheduler.distribute_block_reward("block-1", 10)

            self.assertEqual(result["block_hash"], "block-1")
            self.assertEqual(result["eligible_shares"], 1)
            self.assertEqual(len(result["payouts"]), 1)
            self.assertEqual(result["payouts"][0]["event_type"], "mining_block_reward")
            self.assertGreater(db.get_balance("test-worker"), 9)
            db.close()

    def test_shares_cannot_be_reused_across_rounds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scheduler, db = self._scheduler(tmp)
            scheduler.run_once()

            scheduler.distribute_block_reward("block-1", 10)

            with self.assertRaises(RuntimeError):
                scheduler.distribute_block_reward("block-2", 10)
            db.close()

    def test_mixed_difficulty_pplns_payouts_are_weighted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scheduler, db = self._scheduler(tmp)
            submitted_at = utc_now_iso()
            self._insert_share(db, "worker-a", difficulty=1, submitted_at=submitted_at)
            self._insert_share(db, "worker-b", difficulty=3, submitted_at=submitted_at)

            result = scheduler.distribute_block_reward("weighted-block", 8)

            payouts = {event["worker_id"]: event["qi_amount"] for event in result["payouts"]}
            self.assertEqual(result["eligible_share_weight"], 4)
            self.assertAlmostEqual(payouts["worker-a"], 2)
            self.assertAlmostEqual(payouts["worker-b"], 6)
            self.assertAlmostEqual(db.get_balance("worker-a"), 2)
            self.assertAlmostEqual(db.get_balance("worker-b"), 6)
            db.close()

    def test_cannot_distribute_same_block_twice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scheduler, db = self._scheduler(tmp)
            scheduler.run_once()

            scheduler.distribute_block_reward("block-1", 10)

            with self.assertRaises(ValueError):
                scheduler.distribute_block_reward("block-1", 10)
            db.close()

    def test_failed_mining_command_records_zero_share_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scheduler, db = self._scheduler(tmp, mining_command="false")

            receipt = scheduler.run_once()

            self.assertEqual(receipt["mode"], "mining")
            self.assertEqual(receipt["output"]["amount"], 0)
            self.assertIn("error", receipt["metadata"])
            self.assertEqual(db.get_balance("test-worker"), 0)
            db.close()

    def test_safe_command_execution_requires_argument_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scheduler, db = self._scheduler(tmp)

            with self.assertRaises(ValueError):
                scheduler._run_command("echo unsafe", timeout=1)
            scheduler._run_command(["python3", "-c", ""], timeout=1)
            db.close()

    def test_total_rig_power_is_used_for_energy_accounting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scheduler, db = self._scheduler(
                tmp,
                telemetry=FixedTelemetry([300, 250, 200]),
                cycle_seconds=0.001,
            )

            receipt = scheduler.run_once()

            self.assertEqual(receipt["average_watts"], 750)
            self.assertGreater(receipt["energy_joules"], 0)
            db.close()

    def test_registering_worker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)

            db.register_worker(self._worker("worker-a", models=["llama-3.1-8b"]))

            worker = db.get_worker("worker-a")
            self.assertIsNotNone(worker)
            self.assertEqual(worker["worker_id"], "worker-a")
            self.assertEqual(worker["supported_models"], ["llama-3.1-8b"])
            db.close()

    def test_worker_heartbeat_updates_online_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)
            db.register_worker(self._worker("worker-a", online=False))

            heartbeat_local_worker(db, "worker-a", {"last_seen_at": utc_now_iso(), "total_watts": 250})

            worker = db.get_worker("worker-a")
            self.assertTrue(worker["online"])
            self.assertIsNotNone(worker["last_seen_at"])
            db.close()

    def test_register_worker_preserves_existing_reputation_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)
            db.register_worker(self._worker("worker-a", reputation_score=50))
            update_worker_reputation(
                db,
                worker_id="worker-a",
                verification={"accepted": True, "reason": "receipt accepted"},
                receipt=self._inference_receipt(),
            )

            db.register_worker(self._worker("worker-a", reputation_score=50, models=["llama-3.1-8b", "mistral"]))

            worker = db.get_worker("worker-a")
            self.assertEqual(worker["reputation_score"], 51)
            self.assertEqual(worker["success_count"], 1)
            self.assertIn("mistral", worker["supported_models"])
            db.close()

    def test_routing_chooses_highest_scoring_eligible_worker(self) -> None:
        job = {
            "job_id": "job-route",
            "model": "llama-3.1-8b",
            "requires_gpu": True,
            "region_preference": "us-east",
        }
        workers = [
            self._worker("low", reputation_score=40, region="us-west", models=["llama-3.1-8b"]),
            self._worker("high", reputation_score=80, region="us-east", models=["llama-3.1-8b"]),
        ]

        decision = route_inference_job(job, workers)

        self.assertTrue(decision.accepted)
        self.assertEqual(decision.worker_id, "high")

    def test_routing_rejects_when_no_worker_supports_model(self) -> None:
        decision = route_inference_job(
            {"job_id": "job-route", "model": "unsupported", "requires_gpu": True},
            [self._worker("worker-a", models=["llama-3.1-8b"])],
        )

        self.assertFalse(decision.accepted)
        self.assertIsNone(decision.worker_id)
        self.assertEqual(decision.failure_code, failures.MODEL_NOT_SUPPORTED)

    def test_routing_creates_audit_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)
            db.register_worker(self._worker("worker-a"))
            job = {"job_id": "audit-job", "model": "llama-3.1-8b", "requires_gpu": True}

            decision = route_and_audit_inference_job(db, job, db.list_online_workers())

            logs = db.routing_audit_logs_for_job("audit-job")
            self.assertTrue(decision.accepted)
            self.assertEqual(len(logs), 1)
            self.assertTrue(logs[0]["accepted"])
            db.close()

    def test_rejected_route_creates_audit_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)
            db.register_worker(self._worker("worker-a", models=["llama-3.1-8b"]))

            decision = route_and_audit_inference_job(
                db,
                {"job_id": "audit-reject", "model": "unsupported", "requires_gpu": True},
                db.list_online_workers(),
            )

            logs = db.routing_audit_logs_for_job("audit-reject")
            self.assertFalse(decision.accepted)
            self.assertEqual(logs[0]["reason"], failures.MODEL_NOT_SUPPORTED)
            db.close()

    def test_routing_audit_stores_alternatives(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)
            db.register_worker(self._worker("worker-a", reputation_score=80))
            db.register_worker(self._worker("worker-b", reputation_score=60))

            route_and_audit_inference_job(
                db,
                {"job_id": "audit-alts", "model": "llama-3.1-8b", "requires_gpu": True},
                db.list_online_workers(),
            )

            logs = db.routing_audit_logs_for_job("audit-alts")
            self.assertEqual(logs[0]["alternatives"][0]["worker_id"], "worker-b")
            db.close()

    def test_reputation_increases_after_accepted_verified_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)
            db.register_worker(self._worker("worker-a", reputation_score=50))
            receipt = self._inference_receipt()

            worker = update_worker_reputation(
                db,
                worker_id="worker-a",
                verification={"accepted": True, "reason": "receipt accepted"},
                receipt=receipt,
            )

            self.assertEqual(worker["success_count"], 1)
            self.assertEqual(worker["reputation_score"], 51)
            db.close()

    def test_reputation_decreases_after_failed_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)
            db.register_worker(self._worker("worker-a", reputation_score=50))
            receipt = self._inference_receipt()

            worker = update_worker_reputation(
                db,
                worker_id="worker-a",
                verification={"accepted": False, "reason": "job failed"},
                receipt=receipt,
            )

            self.assertEqual(worker["failure_count"], 1)
            self.assertEqual(worker["reputation_score"], 47)
            db.close()

    def test_pricing_returns_positive_qi_estimate(self) -> None:
        estimate = estimate_job_price(
            input_tokens=100,
            output_tokens=500,
            model="llama-3.1-8b",
            privacy_level="private",
            latency_target=1000,
            energy_joules=100,
            worker_reputation=80,
            config={"pricing": {"energy_rate_qi_per_joule": 0.000000001}},
        )

        self.assertGreater(estimate.estimated_price_qi, 0)
        self.assertEqual(estimate.pricing_basis, "tokens+privacy+latency+reputation+energy")

    def test_customer_job_is_queued_routed_assigned_and_status_updated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)
            db.register_worker(self._worker("worker-a", models=["llama-3.1-8b"]))
            job = self._customer_job("customer-job-1")
            db.insert_customer_job(job)

            queued = db.list_queued_jobs()
            decision = route_inference_job(queued[0], db.list_online_workers())
            db.assign_customer_job(job["job_id"], decision.worker_id, decision.score)
            db.update_customer_job_status(job["job_id"], "completed", {"result": "ok"})

            stored = db.get_customer_job(job["job_id"])
            self.assertEqual(stored["assigned_worker_id"], "worker-a")
            self.assertEqual(stored["status"], "completed")
            self.assertEqual(stored["metadata"]["result"], "ok")
            db.close()

    def test_raw_prompt_is_not_stored_in_customer_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)
            job = self._customer_job("customer-job-privacy")
            job["metadata"] = {"raw_prompt": "secret prompt", "safe": "value"}
            db.insert_customer_job(job)

            stored = db.get_customer_job(job["job_id"])
            self.assertNotIn("raw_prompt", stored["metadata"])
            self.assertNotIn("prompt", stored["metadata"])
            self.assertEqual(stored["metadata"]["safe"], "value")
            db.close()

    def test_valid_job_envelope_passes(self) -> None:
        envelope = self._envelope()

        result = verify_job_envelope(envelope)

        self.assertTrue(result["accepted"])

    def test_job_envelope_missing_prompt_hash_fails(self) -> None:
        envelope = self._envelope()
        envelope["prompt_hash"] = ""

        result = verify_job_envelope(envelope)

        self.assertFalse(result["accepted"])

    def test_job_envelope_missing_nonce_fails(self) -> None:
        envelope = self._envelope()
        envelope["nonce"] = ""

        result = verify_job_envelope(envelope)

        self.assertFalse(result["accepted"])

    def test_envelope_hash_changes_if_job_parameters_change(self) -> None:
        envelope = self._envelope()
        original_hash = envelope["envelope_hash"]
        envelope["input_tokens"] += 1

        self.assertNotEqual(original_hash, compute_envelope_hash(envelope))

    def test_valid_capability_claim_passes(self) -> None:
        claim = make_capability_claim(self._worker("worker-a"))

        result = verify_capability_claim(claim)

        self.assertTrue(result["accepted"])

    def test_capability_claim_missing_worker_id_fails(self) -> None:
        claim = make_capability_claim(self._worker("worker-a"))
        claim["worker_id"] = ""

        result = verify_capability_claim(claim)

        self.assertFalse(result["accepted"])

    def test_capability_claim_missing_supported_models_fails(self) -> None:
        claim = make_capability_claim(self._worker("worker-a"))
        claim["supported_models"] = []

        result = verify_capability_claim(claim)

        self.assertFalse(result["accepted"])

    def test_capability_hash_changes_when_gpu_count_changes(self) -> None:
        claim = make_capability_claim(self._worker("worker-a"))
        original_hash = claim["capability_hash"]
        claim["gpu_count"] += 1

        self.assertNotEqual(original_hash, compute_capability_hash(claim))

    def test_customer_receipt_can_be_built(self) -> None:
        job = self._customer_job("receipt-job")
        decision = route_inference_job({"job_id": "receipt-job", "model": "llama-3.1-8b"}, [self._worker("worker-a")])
        worker_receipt = self._inference_receipt()

        receipt = build_customer_receipt(job, decision, worker_receipt, {"accepted": True, "reason": "ok"})

        self.assertEqual(receipt["job_id"], "receipt-job")
        self.assertEqual(receipt["assigned_worker_id"], "worker-a")

    def test_customer_receipt_does_not_expose_raw_prompt(self) -> None:
        job = self._customer_job("receipt-private")
        job["metadata"] = {"raw_prompt": "secret", "visible": "ok"}
        decision = route_inference_job({"job_id": "receipt-private", "model": "llama-3.1-8b"}, [self._worker("worker-a")])

        receipt = build_customer_receipt(job, decision, self._inference_receipt(), {"accepted": True, "reason": "ok"})

        self.assertNotIn("raw_prompt", receipt["metadata"])
        self.assertEqual(receipt["metadata"]["visible"], "ok")

    def test_customer_receipt_hash_changes_if_final_price_changes(self) -> None:
        job = self._customer_job("receipt-price")
        decision = route_inference_job({"job_id": "receipt-price", "model": "llama-3.1-8b"}, [self._worker("worker-a")])
        receipt = build_customer_receipt(job, decision, self._inference_receipt(), {"accepted": True, "reason": "ok"})
        original_hash = receipt["customer_receipt_hash"]
        receipt["final_price_qi"] += 1

        self.assertNotEqual(original_hash, compute_customer_receipt_hash(receipt))

    def test_failure_codes_are_used_for_major_rejection_paths(self) -> None:
        envelope = self._envelope()
        envelope["nonce"] = ""
        capability = make_capability_claim(self._worker("worker-a"))
        capability["worker_id"] = ""
        route = route_inference_job({"job_id": "job", "model": "missing"}, [self._worker("worker-a")])

        self.assertFalse(verify_job_envelope(envelope)["accepted"])
        self.assertFalse(verify_capability_claim(capability)["accepted"])
        self.assertEqual(route.failure_code, failures.MODEL_NOT_SUPPORTED)

    def test_simulation_runs_without_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)

            summary = run_marketplace_simulation(db, {})

            self.assertEqual(summary["workers_registered"], 2)
            self.assertEqual(summary["jobs_submitted"], 2)
            db.close()

    def test_simulation_produces_routed_job_and_audit_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)

            summary = run_marketplace_simulation(db, {})

            self.assertGreaterEqual(summary["jobs_routed"], 1)
            self.assertGreaterEqual(summary["audit_logs"], 1)
            db.close()

    def _scheduler(
        self,
        tmp: str,
        mining_command: object = "",
        telemetry: object | None = None,
        cycle_seconds: float = 0.001,
    ) -> tuple[Scheduler, WorkerDB]:
        root = Path(tmp)
        config = {
            "worker": {
                "id": "test-worker",
                "operator": "test-operator",
                "public_key": "placeholder-test-key",
                "region": "test-region",
                "hardware_profile": {
                    "gpu_count": 1,
                    "gpu_names": ["test-gpu"],
                    "total_vram_gb": 24,
                    "fallback_watts": 100,
                },
                "db_path": str(root / "worker.db"),
                "fallback_watts": 100,
                "loop_interval_seconds": 0.001,
            },
            "telemetry": {"nvidia_smi_path": "definitely-not-nvidia-smi"},
            "jobs": {
                "queue_dir": str(root / "jobs"),
                "completed_dir": str(root / "done"),
                "failed_dir": str(root / "failed"),
            },
            "mining": {
                "enabled": True,
                "command": mining_command,
                "cycle_seconds": cycle_seconds,
                "pplns_window_weight": 1000,
                "pool_fee_percent": 0,
                "estimated_shares_per_second": 10,
                "estimated_qi_per_share": 0.5,
            },
            "inference": {
                "enabled": True,
                "command": "",
                "default_tokens": 10,
                "seconds_per_job": 0.001,
                "estimated_qi_per_token": 0.25,
            },
        }
        db = WorkerDB(config["worker"]["db_path"])
        telemetry = telemetry or GPUTelemetry(
            nvidia_smi_path=config["telemetry"]["nvidia_smi_path"],
            fallback_watts=config["worker"]["fallback_watts"],
        )
        return Scheduler(config, db, telemetry), db

    def _config_for_verifier(self) -> dict[str, object]:
        return {
            "worker": {
                "id": "test-worker",
                "operator": "test-operator",
                "public_key": "placeholder-test-key",
                "region": "test-region",
            }
        }

    def _inference_receipt(
        self,
        *,
        input_tokens: float = 10,
        output_tokens: float = 20,
    ) -> dict[str, object]:
        return make_receipt(
            worker_id="test-worker",
            mode="inference",
            started_at=utc_now_iso(),
            ended_at=utc_now_iso(),
            duration_seconds=1,
            average_watts=100,
            output_type="tokens",
            output_amount=output_tokens,
            estimated_qi_owed=1,
            metadata={
                "job_id": "job-verify-1",
                "accepted": True,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
        ).to_dict()

    def _insert_share(
        self,
        db: WorkerDB,
        worker_id: str,
        difficulty: float,
        submitted_at: str,
    ) -> None:
        db.insert_mining_share(
            {
                "share_id": str(uuid4()),
                "worker_id": worker_id,
                "submitted_at": submitted_at,
                "difficulty": difficulty,
                "accepted": True,
                "stale": False,
                "metadata": {},
            }
        )

    def _worker(
        self,
        worker_id: str,
        *,
        reputation_score: float = 50,
        region: str = "us-east",
        models: list[str] | None = None,
        online: bool = True,
    ) -> dict[str, object]:
        return {
            "worker_id": worker_id,
            "operator": "operator",
            "region": region,
            "public_key": "placeholder",
            "endpoint": "local",
            "hardware_profile": {"gpu_count": 1, "total_vram_gb": 24},
            "supported_modes": ["inference", "mining"],
            "supported_models": models or ["llama-3.1-8b"],
            "gpu_count": 1,
            "total_vram_gb": 24,
            "total_watts_capacity": 300,
            "online": online,
            "last_seen_at": utc_now_iso(),
            "reputation_score": reputation_score,
            "success_count": 0,
            "failure_count": 0,
            "average_latency_ms": 0,
            "average_energy_per_token": 0,
            "metadata": {},
        }

    def _customer_job(self, job_id: str) -> dict[str, object]:
        return {
            "job_id": job_id,
            "customer_id": "customer",
            "model": "llama-3.1-8b",
            "prompt_hash": "placeholder-hash",
            "input_tokens": 100,
            "expected_output_tokens": 500,
            "privacy_level": "standard",
            "max_price_qi": 0.001,
            "status": "queued",
            "created_at": utc_now_iso(),
            "metadata": {},
        }

    def _envelope(self) -> dict[str, object]:
        return make_job_envelope(
            job_id="envelope-job",
            customer_id="customer",
            model="llama-3.1-8b",
            prompt_hash="placeholder-hash",
            input_tokens=10,
            expected_output_tokens=20,
            privacy_level="standard",
            max_price_qi=0.001,
        )


class FixedTelemetry(GPUTelemetry):
    def __init__(self, watts: list[float]):
        super().__init__(nvidia_smi_path="unused", fallback_watts=100)
        self.watts = watts

    def sample(self) -> list[dict[str, object]]:
        return [
            {
                "ts": utc_now_iso(),
                "gpu_index": index,
                "name": f"GPU {index}",
                "power_watts": watts,
                "source": "test",
            }
            for index, watts in enumerate(self.watts)
        ]


if __name__ == "__main__":
    unittest.main()
