from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from db import WorkerDB
from scheduler import Scheduler
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
        self.assertIn("job id is required", result.reason)

    def test_rejected_inference_receipt_negative_token_count(self) -> None:
        receipt = self._inference_receipt(input_tokens=-1)
        job = {"id": "job-negative", "input_tokens": -1, "output_tokens": 20}

        result = verify_inference_receipt(receipt, job, self._config_for_verifier())

        self.assertFalse(result.accepted)
        self.assertIn("input token count must be non-negative", result.reason)

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
