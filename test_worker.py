from __future__ import annotations

import json
import socket
import tempfile
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from uuid import uuid4

import failures
from adversary import FLAKY, MALICIOUS_RECEIPT, duplicate_job, simulate_capability_claim, simulate_worker_receipt
from challenges import create_challenge, verify_challenge_result
from capabilities import compute_capability_hash, make_capability_claim, verify_capability_claim
from committees import (
    ACCEPTED,
    DISPUTED,
    REJECTED,
    create_verification_committee,
    run_verification_committee,
    select_verifier_workers,
)
from customer_receipts import build_customer_receipt, compute_customer_receipt_hash
from daemon import WorkerDaemon
from doctor import run_checks
from demo import run_demo
from demo_data import demo_prompt
from db import WorkerDB
from envelopes import compute_envelope_hash, make_job_envelope, verify_job_envelope
from epochs import active_epoch, finalize_epoch
from lifecycle import transition_job_status
from logging_config import redact_payload
from pricing import estimate_job_price
from registry import heartbeat_local_worker
from reputation import apply_reputation_decay, update_worker_reputation
from retry import next_retry_status, should_retry
from router import route_and_audit_inference_job, route_inference_job
from runtime import OllamaRuntime, RuntimeResult, SimulatedRuntime, SubprocessRuntime, output_hash
from scheduler import Scheduler
from simulation import run_marketplace_simulation
from stress_simulation import run_stress_simulation
from telemetry import GPUTelemetry
from receipts import make_receipt, utc_now_iso, verify_receipt_hash
from verifier import verify_inference_receipt
from worker import _minimal_yaml_load, load_config
from benchmarks import run_benchmarks


class WorkerPrototypeTest(unittest.TestCase):
    def test_doctor_runs_successfully(self) -> None:
        results = run_checks("config.yaml")
        statuses = {result.status for result in results}

        self.assertIn("PASS", statuses)
        self.assertNotIn("FAIL", statuses)

    def test_makefile_commands_exist(self) -> None:
        text = Path("Makefile").read_text(encoding="utf-8")

        for target in ("test:", "demo:", "stress:", "lint:", "clean:"):
            self.assertIn(target, text)

    def test_architecture_docs_present(self) -> None:
        text = Path("ARCHITECTURE.md").read_text(encoding="utf-8")

        self.assertIn("customer job", text)
        self.assertIn("challenge verification", text)
        self.assertIn("epoch settlement", text)

    def test_example_outputs_present(self) -> None:
        examples = Path("examples")

        for filename in (
            "demo_summary.txt",
            "epoch_summary.txt",
            "worker_summary.txt",
            "committee_summary.txt",
            "failure_output.txt",
        ):
            self.assertTrue((examples / filename).exists())

    def test_logging_redacts_raw_prompt_and_output(self) -> None:
        redacted = redact_payload(
            {
                "prompt": "private prompt",
                "nested": {"raw_output": "private output", "output_hash": "safe"},
            }
        )

        serialized = json.dumps(redacted, sort_keys=True)
        self.assertNotIn("private prompt", serialized)
        self.assertNotIn("private output", serialized)
        self.assertIn("output_hash", serialized)

    def test_github_workflow_file_exists(self) -> None:
        workflow = Path(".github/workflows/tests.yml")

        self.assertTrue(workflow.exists())
        self.assertIn("python -m unittest -v", workflow.read_text(encoding="utf-8"))

    def test_benchmark_stub_runs(self) -> None:
        results = run_benchmarks(iterations=1)

        self.assertIn("simulated", results)
        self.assertIn("subprocess", results)
        self.assertGreater(results["simulated"]["jobs_per_second"], 0)
        self.assertGreaterEqual(results["subprocess"]["tokens_per_second"], 0)

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
            db.update_customer_job_status(job["job_id"], "running", {})
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

    def test_lifecycle_valid_and_invalid_transitions(self) -> None:
        self.assertTrue(transition_job_status("queued", "routed"))
        self.assertTrue(transition_job_status("routed", "running"))
        self.assertTrue(transition_job_status("running", "completed"))
        self.assertFalse(transition_job_status("queued", "completed"))
        self.assertFalse(transition_job_status("completed", "running"))

    def test_expired_queued_job_is_marked_expired(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)
            job = self._customer_job("expired-job")
            job["expires_at"] = "2000-01-01T00:00:00+00:00"
            db.insert_customer_job(job)

            expired = db.expire_stale_customer_jobs(utc_now_iso())

            stored = db.get_customer_job("expired-job")
            self.assertEqual(expired, 1)
            self.assertEqual(stored["status"], "expired")
            self.assertEqual(stored["last_failure_code"], failures.JOB_EXPIRED)
            db.close()

    def test_expired_job_is_not_routed(self) -> None:
        decision = route_inference_job(
            {
                "job_id": "expired-route",
                "model": "llama-3.1-8b",
                "requires_gpu": True,
                "expires_at": "2000-01-01T00:00:00+00:00",
            },
            [self._worker("worker-a")],
        )

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.failure_code, failures.JOB_EXPIRED)

    def test_non_expired_job_still_routes(self) -> None:
        decision = route_inference_job(
            {
                "job_id": "fresh-route",
                "model": "llama-3.1-8b",
                "requires_gpu": True,
                "expires_at": "9999-01-01T00:00:00+00:00",
            },
            [self._worker("worker-a")],
        )

        self.assertTrue(decision.accepted)

    def test_retryable_failure_increments_retry_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)
            job = self._customer_job("retry-job")
            db.insert_customer_job(job)
            db.assign_customer_job("retry-job", "worker-a", 1)
            db.update_customer_job_status("retry-job", "running", {})

            db.mark_customer_job_failure("retry-job", failures.WORKER_TIMEOUT, "timeout", retrying=True)

            stored = db.get_customer_job("retry-job")
            self.assertEqual(stored["status"], "retrying")
            self.assertEqual(stored["retry_count"], 1)
            self.assertEqual(stored["last_failure_code"], failures.WORKER_TIMEOUT)
            db.close()

    def test_max_retries_and_non_retryable_failures_stop_retry(self) -> None:
        retry_job = {"retry_count": 2}
        duplicate_job = {"retry_count": 0}

        self.assertFalse(should_retry(retry_job, failures.WORKER_TIMEOUT, {"retry": {"max_retries": 2}}))
        self.assertFalse(should_retry(duplicate_job, failures.DUPLICATE_JOB, {"retry": {"max_retries": 2}}))
        self.assertEqual(next_retry_status(retry_job, failures.WORKER_TIMEOUT, {"retry": {"max_retries": 2}}), "failed")

    def test_retrying_job_can_be_routed_again(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)
            db.register_worker(self._worker("worker-a"))
            job = self._customer_job("retry-route")
            job["status"] = "retrying"
            job["retry_count"] = 1
            db.insert_customer_job(job)

            queued = db.list_queued_jobs()
            decision = route_inference_job(queued[0], db.list_online_workers())

            self.assertEqual(queued[0]["status"], "retrying")
            self.assertTrue(decision.accepted)
            db.close()

    def test_overloaded_worker_is_skipped(self) -> None:
        decision = route_inference_job(
            {"job_id": "overloaded", "model": "llama-3.1-8b", "requires_gpu": True},
            [self._worker("busy", current_jobs=2, max_concurrent_jobs=2)],
        )

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.failure_code, failures.WORKER_OVERLOADED)

    def test_lower_load_worker_wins_over_equal_higher_load_worker(self) -> None:
        decision = route_inference_job(
            {"job_id": "load-route", "model": "llama-3.1-8b", "requires_gpu": True},
            [
                self._worker("busy", reputation_score=70, current_jobs=1, max_concurrent_jobs=2, load_percent=50),
                self._worker("idle", reputation_score=70, current_jobs=0, max_concurrent_jobs=2, load_percent=0),
            ],
        )

        self.assertTrue(decision.accepted)
        self.assertEqual(decision.worker_id, "idle")

    def test_load_increments_and_decrements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)
            db.register_worker(self._worker("worker-a", max_concurrent_jobs=2))

            db.increment_worker_load("worker-a")
            loaded = db.get_worker("worker-a")
            db.decrement_worker_load("worker-a")
            unloaded = db.get_worker("worker-a")

            self.assertEqual(loaded["current_jobs"], 1)
            self.assertEqual(loaded["load_percent"], 50)
            self.assertEqual(unloaded["current_jobs"], 0)
            self.assertEqual(unloaded["load_percent"], 0)
            db.close()

    def test_simulation_summary_includes_distributed_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)

            summary = run_marketplace_simulation(db, {})

            for key in {
                "online_workers",
                "offline_workers",
                "jobs_completed",
                "jobs_retried",
                "jobs_expired",
                "jobs_failed",
                "average_latency",
                "route_success_rate",
            }:
                self.assertIn(key, summary)
            db.close()

    def test_malicious_receipt_fails_verification(self) -> None:
        receipt = simulate_worker_receipt(
            "worker-a",
            self._customer_job("malicious-job"),
            MALICIOUS_RECEIPT,
        )

        self.assertFalse(verify_receipt_hash(receipt))

    def test_fake_capability_claim_is_rejected(self) -> None:
        claim = simulate_capability_claim(self._worker("worker-a"), "fake_capability")

        self.assertFalse(verify_capability_claim(claim)["accepted"])

    def test_duplicate_job_does_not_create_payout_or_reputation_gain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scheduler, db = self._scheduler(tmp)
            db.register_worker(self._worker("test-worker", reputation_score=50))
            job_dir = Path(tmp) / "jobs"
            job_dir.mkdir(exist_ok=True)
            job = {"id": "dupe-adversary", "input_tokens": 1, "output_tokens": 2, "seconds": 0.001}
            (job_dir / "first.json").write_text(json.dumps(job), encoding="utf-8")
            scheduler.run_once()
            first_balance = db.get_settled_balance("test-worker")
            first_reputation = db.get_worker("test-worker")["reputation_score"]
            replay = duplicate_job(job)
            replay["id"] = replay["job_id"] = "dupe-adversary"
            (job_dir / "second.json").write_text(json.dumps(replay), encoding="utf-8")

            scheduler.run_once()
            update_worker_reputation(
                db,
                worker_id="test-worker",
                verification={"accepted": True, "reason": "duplicate"},
                receipt=self._inference_receipt(),
                duplicate_job=True,
            )

            self.assertEqual(db.get_settled_balance("test-worker"), first_balance)
            self.assertEqual(db.get_worker("test-worker")["reputation_score"], first_reputation)
            db.close()

    def test_flaky_worker_reputation_decreases_over_repeated_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)
            db.register_worker(self._worker("flaky", reputation_score=50))

            for i in range(3):
                receipt = simulate_worker_receipt("flaky", self._customer_job(f"flaky-{i}"), FLAKY, attempt=0)
                update_worker_reputation(
                    db,
                    worker_id="flaky",
                    verification={"accepted": False, "reason": "job failed"},
                    receipt=receipt,
                )

            worker = db.get_worker("flaky")
            self.assertEqual(worker["failure_count"], 3)
            self.assertLess(worker["reputation_score"], 41)
            db.close()

    def test_stale_worker_reputation_decays(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)
            worker = self._worker("stale", reputation_score=50)
            worker["last_seen_at"] = "2026-05-01T00:00:00+00:00"
            db.register_worker(worker)

            updated = apply_reputation_decay(
                db,
                worker_id="stale",
                now="2026-06-01T00:00:00+00:00",
                config={"reputation": {"decay_per_day": 1, "offline_penalty": 0}},
            )

            self.assertEqual(updated["reputation_score"], 19)
            db.close()

    def test_offline_worker_routes_lower_than_online_worker(self) -> None:
        decision = route_inference_job(
            {"job_id": "offline-route", "model": "llama-3.1-8b", "requires_gpu": True},
            [
                self._worker("offline", reputation_score=100, online=False),
                self._worker("online", reputation_score=50, online=True),
            ],
        )

        self.assertTrue(decision.accepted)
        self.assertEqual(decision.worker_id, "online")

    def test_repeated_failures_penalize_more_than_one_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)
            db.register_worker(self._worker("worker-a", reputation_score=50))
            receipt = self._inference_receipt()

            first = update_worker_reputation(
                db,
                worker_id="worker-a",
                verification={"accepted": False, "reason": "job failed"},
                receipt=receipt,
            )
            second = update_worker_reputation(
                db,
                worker_id="worker-a",
                verification={"accepted": False, "reason": "job failed"},
                receipt=receipt,
            )

            self.assertLess(second["reputation_score"], first["reputation_score"] - 2.9)
            db.close()

    def test_reputation_bounds_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)
            db.register_worker(self._worker("low", reputation_score=1))
            db.register_worker(self._worker("high", reputation_score=100))

            for _ in range(20):
                update_worker_reputation(
                    db,
                    worker_id="low",
                    verification={"accepted": False, "reason": "verification failed"},
                    receipt=self._inference_receipt(),
                )
                update_worker_reputation(
                    db,
                    worker_id="high",
                    verification={"accepted": True, "reason": "ok"},
                    receipt=self._inference_receipt(),
                )

            self.assertEqual(db.get_worker("low")["reputation_score"], 0)
            self.assertEqual(db.get_worker("high")["reputation_score"], 100)
            db.close()

    def test_stress_simulation_runs_deterministically_and_completes_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db1 = self._scheduler(tmp)
            summary1 = run_stress_simulation(db1, {}, seed=7)
            db1.close()

        with tempfile.TemporaryDirectory() as tmp:
            _, db2 = self._scheduler(tmp)
            summary2 = run_stress_simulation(db2, {}, seed=7)
            db2.close()

        self.assertEqual(summary1, summary2)
        self.assertGreater(summary1["completed"], 0)
        self.assertIn("average_final_price", summary1)
        self.assertTrue(summary1["malicious_worker_penalty_observed"])
        self.assertEqual(summary1["total_epochs"], 1)
        self.assertIn("committee_acceptance_rate", summary1)
        self.assertIn("dispute_rate", summary1)
        self.assertIn("verifier_disagreement_rate", summary1)
        self.assertAlmostEqual(summary1["epoch_totals"]["total_settled_qi"], summary1["settled_qi_total"])
        self.assertEqual(
            summary1["epoch_totals"]["accepted_committee_count"],
            summary1["completed"],
        )

    def test_honest_worker_passes_deterministic_challenge(self) -> None:
        job = {"id": "challenge-job", "tokens": 20}
        challenge = create_challenge(job, "worker-a", {"challenges": {"enabled": True, "challenge_rate": 1}})
        receipt = self._inference_receipt(output_tokens=20)
        receipt["metadata"]["job_id"] = "challenge-job"
        receipt["metadata"]["challenge_response_hash"] = challenge["expected_hash"]
        receipt["receipt_hash"] = verify_receipt_hash(receipt) and receipt["receipt_hash"]

        result = verify_challenge_result(challenge, receipt)

        self.assertTrue(result.accepted)
        self.assertEqual(result.reason, "challenge accepted")

    def test_malformed_receipt_fails_challenge(self) -> None:
        job = {"id": "challenge-bad", "tokens": 20}
        challenge = create_challenge(job, "worker-a", {"challenges": {"enabled": True, "challenge_rate": 1}})
        receipt = self._inference_receipt(output_tokens=20)
        receipt["metadata"]["job_id"] = "challenge-bad"
        receipt["metadata"]["challenge_response_hash"] = "wrong"

        result = verify_challenge_result(challenge, receipt)

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, failures.CHALLENGE_FAILED)
        self.assertIn("challenge response hash mismatch", result.metadata["reason_detail"])

    def test_failed_challenge_reduces_reputation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)
            db.register_worker(self._worker("worker-a", reputation_score=50))
            receipt = self._inference_receipt()

            worker = update_worker_reputation(
                db,
                worker_id="worker-a",
                verification={"accepted": False, "reason": failures.CHALLENGE_FAILED},
                receipt=receipt,
            )

            self.assertEqual(worker["failure_count"], 1)
            self.assertEqual(worker["reputation_score"], 40)
            db.close()

    def test_expired_challenge_is_handled(self) -> None:
        job = {"id": "challenge-expired", "tokens": 20}
        challenge = create_challenge(
            job,
            "worker-a",
            {"challenges": {"enabled": True, "challenge_rate": 1, "ttl_seconds": -1}},
        )
        receipt = self._inference_receipt(output_tokens=20)
        receipt["metadata"]["job_id"] = "challenge-expired"
        receipt["metadata"]["challenge_response_hash"] = challenge["expected_hash"]

        result = verify_challenge_result(challenge, receipt)

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, failures.CHALLENGE_EXPIRED)

    def test_failed_challenge_prevents_payout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs"
            job_dir.mkdir()
            (job_dir / "job.json").write_text(
                json.dumps(
                    {
                        "id": "challenge-payout-blocked",
                        "input_tokens": 1,
                        "output_tokens": 20,
                        "seconds": 0.001,
                        "challenge_response_hash": "wrong",
                    }
                ),
                encoding="utf-8",
            )
            scheduler, db = self._scheduler(
                tmp,
                challenges_config={"enabled": True, "challenge_rate": 1, "ttl_seconds": 300},
            )
            db.register_worker(self._worker("test-worker", reputation_score=50))

            receipt = scheduler.run_once()

            self.assertEqual(receipt["metadata"]["verification"]["reason"], failures.CHALLENGE_FAILED)
            self.assertEqual(db.get_settled_balance("test-worker"), 0)
            self.assertEqual(db.recent_payout_events(1), [])
            results = db.challenge_results_for_job("challenge-payout-blocked")
            self.assertEqual(len(results), 1)
            self.assertFalse(results[0]["accepted"])
            self.assertEqual(db.get_worker("test-worker")["reputation_score"], 40)
            db.close()

    def test_epoch_aggregates_verified_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs"
            job_dir.mkdir()
            (job_dir / "job.json").write_text(
                json.dumps({"id": "epoch-job", "input_tokens": 1, "output_tokens": 4, "seconds": 0.001}),
                encoding="utf-8",
            )
            scheduler, db = self._scheduler(tmp)

            receipt = scheduler.run_once()
            epoch = db.active_epoch()
            summary = finalize_epoch(db, epoch["epoch_id"])

            self.assertEqual(summary["status"], "finalized")
            self.assertEqual(summary["receipt_count"], 1)
            self.assertEqual(summary["total_verified_jobs"], 1)
            self.assertEqual(summary["total_tokens"], receipt["output"]["amount"])
            self.assertGreater(summary["total_settled_qi"], 0)
            self.assertIn("test-worker", summary["metadata"]["worker_totals"])
            db.close()

    def test_epoch_excludes_failed_challenge_and_duplicate_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs"
            job_dir.mkdir()
            scheduler, db = self._scheduler(
                tmp,
                challenges_config={"enabled": True, "challenge_rate": 1},
            )
            epoch = active_epoch(db)
            bad_job = {
                "id": "epoch-bad-challenge",
                "input_tokens": 1,
                "output_tokens": 4,
                "seconds": 0.001,
                "challenge_response_hash": "wrong",
            }
            (job_dir / "bad.json").write_text(json.dumps(bad_job), encoding="utf-8")
            scheduler.run_once()
            good_job = {"id": "epoch-duplicate", "input_tokens": 1, "output_tokens": 4, "seconds": 0.001}
            (job_dir / "good-a.json").write_text(json.dumps(good_job), encoding="utf-8")
            scheduler.run_once()
            (job_dir / "good-b.json").write_text(json.dumps(good_job), encoding="utf-8")
            scheduler.run_once()

            summary = finalize_epoch(db, epoch["epoch_id"])

            self.assertEqual(summary["receipt_count"], 1)
            self.assertEqual(summary["total_verified_jobs"], 1)
            self.assertEqual(summary["metadata"]["challenge_fail_count"], 0)
            self.assertGreater(summary["total_settled_qi"], 0)
            with self.assertRaises(ValueError):
                finalize_epoch(db, epoch["epoch_id"])
            db.close()

    def test_quorum_accepts_valid_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)
            for worker_id, reputation in [("assigned", 90), ("v1", 80), ("v2", 70), ("v3", 60)]:
                db.register_worker(self._worker(worker_id, reputation_score=reputation))
            receipt = self._inference_receipt()
            committee = create_verification_committee(
                db,
                challenge_id=None,
                assigned_worker_id="assigned",
                committee_size=3,
                quorum_threshold=2,
            )

            result = run_verification_committee(db, committee, receipt=receipt, challenge_result={"accepted": True})

            self.assertEqual(result["result"], ACCEPTED)
            self.assertEqual(len(result["votes"]), 3)
            self.assertNotIn("assigned", result["verifier_worker_ids"])
            db.close()

    def test_quorum_rejects_tampered_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)
            for worker_id in ["assigned", "v1", "v2", "v3"]:
                db.register_worker(self._worker(worker_id))
            receipt = self._inference_receipt()
            receipt["output"]["amount"] = 999
            committee = create_verification_committee(
                db,
                challenge_id=None,
                assigned_worker_id="assigned",
                committee_size=3,
                quorum_threshold=2,
            )

            result = run_verification_committee(db, committee, receipt=receipt, challenge_result={"accepted": True})

            self.assertEqual(result["result"], REJECTED)
            self.assertEqual(result["metadata"]["failure_code"], failures.COMMITTEE_REJECTED)
            db.close()

    def test_split_vote_becomes_disputed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, db = self._scheduler(tmp)
            for worker_id in ["assigned", "v1", "v2"]:
                db.register_worker(self._worker(worker_id))
            receipt = self._inference_receipt()
            committee = create_verification_committee(
                db,
                challenge_id=None,
                assigned_worker_id="assigned",
                committee_size=2,
                quorum_threshold=2,
            )

            result = run_verification_committee(
                db,
                committee,
                receipt=receipt,
                challenge_result={"accepted": True},
                forced_votes={"v1": ACCEPTED, "v2": REJECTED},
            )

            self.assertEqual(result["result"], DISPUTED)
            self.assertEqual(result["metadata"]["failure_code"], failures.COMMITTEE_DISPUTED)
            db.close()

    def test_assigned_worker_never_selected_as_verifier(self) -> None:
        workers = [
            self._worker("assigned", reputation_score=100),
            self._worker("v1", reputation_score=90),
            self._worker("v2", reputation_score=80),
        ]

        selected = select_verifier_workers(workers, assigned_worker_id="assigned", committee_size=2)

        self.assertEqual(selected, ["v1", "v2"])

    def test_committee_dispute_blocks_scheduler_payout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "jobs"
            job_dir.mkdir()
            (job_dir / "job.json").write_text(
                json.dumps({"id": "committee-blocked", "input_tokens": 1, "output_tokens": 4, "seconds": 0.001}),
                encoding="utf-8",
            )
            scheduler, db = self._scheduler(
                tmp,
                committees_config={
                    "enabled": True,
                    "committee_size": 2,
                    "quorum_threshold": 2,
                    "forced_votes": {"v1": ACCEPTED, "v2": REJECTED},
                },
            )
            db.register_worker(self._worker("test-worker", reputation_score=50))
            db.register_worker(self._worker("v1", reputation_score=80))
            db.register_worker(self._worker("v2", reputation_score=70))

            receipt = scheduler.run_once()

            self.assertEqual(receipt["metadata"]["verification"]["reason"], failures.COMMITTEE_DISPUTED)
            self.assertEqual(db.get_settled_balance("test-worker"), 0)
            self.assertEqual(db.get_worker("test-worker")["reputation_score"], 43)
            db.close()

    def test_runtime_result_structure(self) -> None:
        result = RuntimeResult(
            job_id="runtime-job",
            worker_id="worker-a",
            model="llama-3.1-8b",
            started_at=utc_now_iso(),
            ended_at=utc_now_iso(),
            duration_seconds=1,
            input_tokens=1,
            output_tokens=2,
            output_hash=output_hash("output"),
            exit_code=0,
            accepted=True,
            error_code=None,
            error_message=None,
            metadata={"runtime_type": "test"},
        )

        data = result.to_dict()

        self.assertEqual(data["job_id"], "runtime-job")
        self.assertEqual(data["output_hash"], output_hash("output"))
        self.assertTrue(data["accepted"])

    def test_simulated_runtime_success(self) -> None:
        runtime = SimulatedRuntime()
        _, db = self._scheduler(tempfile.mkdtemp())
        config = self._daemon_config(Path(db.path).parent)
        job = self._assigned_job("sim-runtime")

        result = runtime.run(job, config)

        self.assertTrue(result.accepted)
        self.assertEqual(result.job_id, "sim-runtime")
        self.assertEqual(result.output_tokens, job["expected_output_tokens"])
        self.assertEqual(result.metadata["runtime_type"], "simulated")
        db.close()

    def test_subprocess_runtime_success(self) -> None:
        runtime = SubprocessRuntime()
        config = self._daemon_config(Path(tempfile.mkdtemp()))
        config["runtime"]["type"] = "subprocess"
        config["runtime"]["command"] = ["python3", "-c", "print('hello runtime')"]
        job = self._assigned_job("subprocess-ok")

        result = runtime.run(job, config)

        self.assertTrue(result.accepted)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.output_hash, output_hash("hello runtime\n"))

    def test_subprocess_runtime_timeout(self) -> None:
        runtime = SubprocessRuntime()
        config = self._daemon_config(Path(tempfile.mkdtemp()))
        config["runtime"]["type"] = "subprocess"
        config["runtime"]["timeout_seconds"] = 0.01
        config["runtime"]["command"] = ["python3", "-c", "import time; time.sleep(1)"]

        result = runtime.run(self._assigned_job("subprocess-timeout"), config)

        self.assertFalse(result.accepted)
        self.assertEqual(result.error_code, failures.WORKER_TIMEOUT)

    def test_subprocess_runtime_nonzero_failure(self) -> None:
        runtime = SubprocessRuntime()
        config = self._daemon_config(Path(tempfile.mkdtemp()))
        config["runtime"]["type"] = "subprocess"
        config["runtime"]["command"] = ["python3", "-c", "import sys; sys.exit(7)"]

        result = runtime.run(self._assigned_job("subprocess-fail"), config)

        self.assertFalse(result.accepted)
        self.assertEqual(result.exit_code, 7)
        self.assertEqual(result.error_code, failures.COMMAND_FAILED)

    def test_subprocess_runtime_rejects_shell_string(self) -> None:
        runtime = SubprocessRuntime()
        config = self._daemon_config(Path(tempfile.mkdtemp()))
        config["runtime"]["type"] = "subprocess"
        config["runtime"]["command"] = "echo unsafe"

        with self.assertRaises(ValueError):
            runtime.run(self._assigned_job("subprocess-shell"), config)

    def test_ollama_runtime_success_with_mocked_response(self) -> None:
        runtime = OllamaRuntime()
        config = self._daemon_config(Path(tempfile.mkdtemp()))
        config["runtime"]["type"] = "ollama"
        job = self._assigned_job("ollama-ok")
        job["prompt"] = "private prompt"
        response = {"response": "private model output", "eval_count": 3}

        with patched_urlopen(response):
            result = runtime.run(job, config)

        self.assertTrue(result.accepted)
        self.assertEqual(result.output_hash, output_hash("private model output"))
        self.assertEqual(result.output_tokens, 3)
        self.assertEqual(result.metadata["runtime_type"], "ollama")
        self.assertEqual(result.metadata["prompt_hash"], output_hash("private prompt"))

    def test_ollama_runtime_connection_failure(self) -> None:
        runtime = OllamaRuntime()
        config = self._daemon_config(Path(tempfile.mkdtemp()))
        config["runtime"]["type"] = "ollama"

        with patched_urlopen_error(urllib.error.URLError("refused")):
            result = runtime.run(self._assigned_job("ollama-offline"), config)

        self.assertFalse(result.accepted)
        self.assertEqual(result.error_code, failures.WORKER_OFFLINE)

    def test_ollama_runtime_timeout(self) -> None:
        runtime = OllamaRuntime()
        config = self._daemon_config(Path(tempfile.mkdtemp()))
        config["runtime"]["type"] = "ollama"

        with patched_urlopen_error(socket.timeout("timeout")):
            result = runtime.run(self._assigned_job("ollama-timeout"), config)

        self.assertFalse(result.accepted)
        self.assertEqual(result.error_code, failures.WORKER_TIMEOUT)

    def test_ollama_runtime_invalid_response(self) -> None:
        runtime = OllamaRuntime()
        config = self._daemon_config(Path(tempfile.mkdtemp()))
        config["runtime"]["type"] = "ollama"

        with patched_urlopen_raw(b"not-json"):
            result = runtime.run(self._assigned_job("ollama-invalid"), config)

        self.assertFalse(result.accepted)
        self.assertEqual(result.error_code, failures.RUNTIME_INVALID_RESPONSE)

    def test_ollama_runtime_does_not_return_raw_prompt_or_output_metadata(self) -> None:
        runtime = OllamaRuntime()
        config = self._daemon_config(Path(tempfile.mkdtemp()))
        config["runtime"]["type"] = "ollama"
        job = self._assigned_job("ollama-private")
        job["prompt"] = "secret prompt"

        with patched_urlopen({"response": "secret output"}):
            result = runtime.run(job, config)

        metadata_json = json.dumps(result.metadata, sort_keys=True)
        self.assertNotIn("secret prompt", metadata_json)
        self.assertNotIn("secret output", metadata_json)
        self.assertEqual(result.output_hash, output_hash("secret output"))

    def test_daemon_processes_one_assigned_job_and_creates_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._daemon_config(Path(tmp))
            db = WorkerDB(config["worker"]["db_path"])
            job = self._assigned_job("daemon-job")
            job["metadata"] = {"raw_prompt": "secret prompt", "visible": "ok"}
            db.insert_customer_job(job)
            daemon = WorkerDaemon(config, db, FixedTelemetry([100]))

            receipt = daemon.run_once(runtime_type="simulated")

            stored = db.get_customer_job("daemon-job")
            receipts = db.recent_receipts(1)
            self.assertIsNotNone(receipt)
            self.assertEqual(stored["status"], "completed")
            self.assertEqual(receipts[0]["receipt_id"], receipt["receipt_id"])
            self.assertEqual(db.get_worker("test-worker")["current_jobs"], 0)
            db.close()

    def test_daemon_does_not_store_raw_prompt_or_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._daemon_config(Path(tmp))
            db = WorkerDB(config["worker"]["db_path"])
            job = self._assigned_job("daemon-private")
            job["metadata"] = {"raw_prompt": "do not store this", "prompt": "also private"}
            db.insert_customer_job(job)
            daemon = WorkerDaemon(config, db, FixedTelemetry([100]))

            receipt = daemon.run_once(runtime_type="simulated")

            metadata_json = json.dumps(receipt["metadata"], sort_keys=True)
            self.assertNotIn("do not store this", metadata_json)
            self.assertNotIn("also private", metadata_json)
            self.assertIn("output_hash", receipt["metadata"])
            self.assertNotIn("raw_output", metadata_json)
            db.close()

    def test_daemon_handles_ollama_unavailable_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._daemon_config(Path(tmp))
            config["runtime"]["type"] = "ollama"
            db = WorkerDB(config["worker"]["db_path"])
            job = self._assigned_job("daemon-ollama-offline")
            job["metadata"] = {"safe": "value"}
            db.insert_customer_job(job)
            daemon = WorkerDaemon(config, db, FixedTelemetry([100]))

            with patched_urlopen_error(urllib.error.URLError("refused")):
                receipt = daemon.run_once(runtime_type="ollama")

            stored = db.get_customer_job("daemon-ollama-offline")
            self.assertIsNotNone(receipt)
            self.assertEqual(stored["status"], "failed")
            self.assertEqual(stored["last_failure_code"], failures.WORKER_OFFLINE)
            self.assertEqual(receipt["metadata"]["runtime"]["error_code"], failures.WORKER_OFFLINE)
            db.close()

    def test_output_hash_is_deterministic(self) -> None:
        self.assertEqual(output_hash("same output"), output_hash("same output"))
        self.assertNotEqual(output_hash("same output"), output_hash("different output"))

    def test_full_demo_runs_successfully(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patched_urlopen({"response": "demo useful output", "eval_count": 32}):
                result = run_demo(db_path=str(Path(tmp) / "demo.db"))

            self.assertEqual(result["job"]["status"], "completed")
            self.assertGreater(result["epoch"]["total_settled_qi"], 0)
            self.assertEqual(result["committee"]["result"], "accepted")

    def test_honest_demo_produces_settled_payout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patched_urlopen({"response": "honest useful output", "eval_count": 32}):
                result = run_demo(mode="honest", db_path=str(Path(tmp) / "demo.db"))

            self.assertEqual(result["metrics"]["jobs_completed"], 1)
            self.assertGreater(result["metrics"]["settled_qi_total"], 0)
            self.assertEqual(result["metrics"]["committee_acceptance_rate"], 1.0)

    def test_malicious_demo_blocks_payout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patched_urlopen({"response": "malicious output", "eval_count": 32}):
                result = run_demo(mode="malicious", db_path=str(Path(tmp) / "demo.db"))

            self.assertEqual(result["job"]["status"], "failed")
            self.assertEqual(result["metrics"]["settled_qi_total"], 0)
            self.assertEqual(result["receipt"]["metadata"]["verification"]["reason"], failures.CHALLENGE_FAILED)

    def test_flaky_demo_reduces_reputation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patched_urlopen_error(urllib.error.URLError("refused")):
                result = run_demo(mode="flaky", db_path=str(Path(tmp) / "demo.db"))

            self.assertEqual(result["job"]["status"], "failed")
            self.assertLess(result["worker"]["reputation_score"], 50)
            self.assertEqual(result["metrics"]["jobs_rejected"], 1)

    def test_demo_epoch_finalizes_correctly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patched_urlopen({"response": "epoch output", "eval_count": 32}):
                result = run_demo(mode="honest", db_path=str(Path(tmp) / "demo.db"))

            self.assertEqual(result["epoch"]["status"], "finalized")
            self.assertEqual(result["epoch"]["receipt_count"], 1)
            self.assertIn("accepted_committee_count", result["epoch"]["metadata"])

    def test_demo_summary_output_contains_expected_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = StringIO()
            with patched_urlopen({"response": "summary output", "eval_count": 32}):
                with redirect_stdout(output):
                    run_demo(mode="honest", db_path=str(Path(tmp) / "demo.db"))

            text = output.getvalue()
            self.assertIn("Settlement Epoch", text)
            self.assertIn("Marketplace Metrics", text)
            self.assertIn("committee_acceptance_rate", text)
            self.assertIn("payout eligibility", text)

    def test_demo_does_not_persist_raw_prompt_or_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw_output = "private demo output"
            with patched_urlopen({"response": raw_output, "eval_count": 32}):
                result = run_demo(mode="honest", db_path=str(Path(tmp) / "demo.db"))

            serialized = json.dumps(result, sort_keys=True)
            self.assertNotIn(demo_prompt("honest"), serialized)
            self.assertNotIn(raw_output, serialized)
            self.assertIn("output_hash", serialized)

    def _scheduler(
        self,
        tmp: str,
        mining_command: object = "",
        telemetry: object | None = None,
        cycle_seconds: float = 0.001,
        challenges_config: dict[str, object] | None = None,
        committees_config: dict[str, object] | None = None,
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
            "runtime": {
                "type": "simulated",
                "timeout_seconds": 300,
                "max_concurrent_jobs": 1,
                "command": [],
                "redact_outputs": True,
                "store_output_hash_only": True,
            },
            "challenges": challenges_config or {"enabled": False, "challenge_rate": 0},
            "committees": committees_config or {"enabled": False},
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
        current_jobs: int = 0,
        max_concurrent_jobs: int = 2,
        load_percent: float | None = None,
    ) -> dict[str, object]:
        now = utc_now_iso()
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
            "last_seen_at": now,
            "reputation_score": reputation_score,
            "success_count": 0,
            "failure_count": 0,
            "average_latency_ms": 0,
            "average_energy_per_token": 0,
            "current_jobs": current_jobs,
            "max_concurrent_jobs": max_concurrent_jobs,
            "load_percent": 100 * current_jobs / max_concurrent_jobs if load_percent is None else load_percent,
            "last_heartbeat_at": now,
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
            "expires_at": "9999-01-01T00:00:00+00:00",
            "metadata": {},
        }

    def _assigned_job(self, job_id: str) -> dict[str, object]:
        job = self._customer_job(job_id)
        job["status"] = "routed"
        job["assigned_worker_id"] = "test-worker"
        job["route_score"] = 1.0
        return job

    def _daemon_config(self, root: Path) -> dict[str, object]:
        return {
            "worker": {
                "id": "test-worker",
                "operator": "test-operator",
                "public_key": "placeholder-test-key",
                "region": "test-region",
                "hardware_profile": {
                    "gpu_count": 1,
                    "gpu_names": ["test-gpu"],
                    "total_vram_gb": 24,
                    "total_watts_capacity": 100,
                },
                "supported_modes": ["inference", "mining"],
                "supported_models": ["llama-3.1-8b"],
                "db_path": str(root / "worker.db"),
                "fallback_watts": 100,
                "loop_interval_seconds": 0.001,
            },
            "telemetry": {"nvidia_smi_path": "definitely-not-nvidia-smi"},
            "inference": {
                "estimated_qi_per_input_token": 0.25,
                "estimated_qi_per_output_token": 0.25,
            },
            "runtime": {
                "type": "simulated",
                "timeout_seconds": 300,
                "max_concurrent_jobs": 1,
                "command": [],
                "redact_outputs": True,
                "store_output_hash_only": True,
            },
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


class MockHTTPResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self) -> "MockHTTPResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


class patched_urlopen:
    def __init__(self, payload: dict[str, object]):
        self.payload = json.dumps(payload).encode("utf-8")
        self.original = urllib.request.urlopen

    def __enter__(self) -> None:
        urllib.request.urlopen = lambda request, timeout=None: MockHTTPResponse(self.payload)

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        urllib.request.urlopen = self.original


class patched_urlopen_raw:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.original = urllib.request.urlopen

    def __enter__(self) -> None:
        urllib.request.urlopen = lambda request, timeout=None: MockHTTPResponse(self.payload)

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        urllib.request.urlopen = self.original


class patched_urlopen_error:
    def __init__(self, error: Exception):
        self.error = error
        self.original = urllib.request.urlopen

    def __enter__(self) -> None:
        def raise_error(request: object, timeout: object = None) -> object:
            raise self.error

        urllib.request.urlopen = raise_error

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        urllib.request.urlopen = self.original


if __name__ == "__main__":
    unittest.main()
