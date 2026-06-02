from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from db import WorkerDB
from scheduler import Scheduler
from telemetry import GPUTelemetry
from worker import load_config


class WorkerPrototypeTest(unittest.TestCase):
    def test_load_config_without_pyyaml_shape(self) -> None:
        config = load_config("config.yaml")

        self.assertEqual(config["worker"]["id"], "local-gpu-rig-001")
        self.assertIn("mining", config)
        self.assertIn("inference", config)

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
            self.assertGreater(db.get_balance("test-worker"), 0)
            self.assertEqual(payout_events[0]["event_type"], "mining_share")
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

    def test_failed_mining_command_records_zero_share_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scheduler, db = self._scheduler(tmp, mining_command="false")

            receipt = scheduler.run_once()

            self.assertEqual(receipt["mode"], "mining")
            self.assertEqual(receipt["output"]["amount"], 0)
            self.assertIn("error", receipt["metadata"])
            self.assertEqual(db.get_balance("test-worker"), 0)
            db.close()

    def _scheduler(self, tmp: str, mining_command: str = "") -> tuple[Scheduler, WorkerDB]:
        root = Path(tmp)
        config = {
            "worker": {
                "id": "test-worker",
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
                "cycle_seconds": 0.001,
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
        telemetry = GPUTelemetry(
            nvidia_smi_path=config["telemetry"]["nvidia_smi_path"],
            fallback_watts=config["worker"]["fallback_watts"],
        )
        return Scheduler(config, db, telemetry), db


if __name__ == "__main__":
    unittest.main()
