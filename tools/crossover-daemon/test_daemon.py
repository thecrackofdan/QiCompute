from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import daemon as crossover
import report
from daemon import (
    CrossoverDB,
    CrossoverEngine,
    MODE_INFERENCE,
    MODE_MINING,
    gather_economics,
    inference_gross_usd_micro_per_day,
    json_path,
    micro_to_str,
    mining_gross_usd_micro_per_day,
    parse_difficulty,
    power_cost_usd_micro_per_day,
    to_micro,
)


def _engine(**overrides) -> CrossoverEngine:
    settings = {
        "margin_percent": 15,
        "consecutive_decisions": 3,
        "min_dwell_seconds": 1800,
        "margin_floor_usd_micro": 50_000,
    }
    settings.update(overrides)
    return CrossoverEngine(**settings)


class CrossoverDaemonTest(unittest.TestCase):
    # ---- money math -------------------------------------------------------

    def test_money_conversion_is_exact_integers(self) -> None:
        self.assertEqual(to_micro("0.12"), 120_000)
        self.assertEqual(to_micro("0.000001"), 1)
        self.assertEqual(to_micro(3), 3_000_000)
        self.assertEqual(micro_to_str(120_000), "0.120000")
        self.assertEqual(micro_to_str(-1_500_000), "-1.500000")

    def test_mining_revenue_integer_math(self) -> None:
        # 45 MH/s, difficulty 1e12 hashes/block, 3 Qi reward, $0.10/Qi
        gross = mining_gross_usd_micro_per_day(
            hashrate_hps=45_000_000,
            network_difficulty=1_000_000_000_000,
            block_reward_micro_qi=to_micro("3"),
            qi_price_micro_usd=to_micro("0.10"),
        )
        # blocks/day = 45e6*86400/1e12 = 3.888; qi/day = 11.664; usd/day = 1.1664
        self.assertEqual(gross, 1_166_400)
        self.assertEqual(
            mining_gross_usd_micro_per_day(
                hashrate_hps=45_000_000,
                network_difficulty=0,
                block_reward_micro_qi=to_micro("3"),
                qi_price_micro_usd=to_micro("0.10"),
            ),
            0,
        )

    def test_inference_and_power_integer_math(self) -> None:
        self.assertEqual(
            inference_gross_usd_micro_per_day(rate_micro_usd_per_hour=to_micro("0.20"), utilization_percent=50),
            2_400_000,
        )
        # 300W for 24h at $0.12/kWh = 7.2 kWh * 0.12 = $0.864
        self.assertEqual(
            power_cost_usd_micro_per_day(watts=300, usd_per_kwh_micro=to_micro("0.12")),
            864_000,
        )

    # ---- switching logic --------------------------------------------------

    def test_switch_requires_consecutive_decisions(self) -> None:
        engine = _engine(min_dwell_seconds=0)
        for step in range(2):
            decision = engine.evaluate(
                mining_net_usd_micro=1_000_000,
                inference_net_usd_micro=2_000_000,
                feeds_ok=True,
                now_seconds=step * 60,
            )
            self.assertFalse(decision["switched"])
        decision = engine.evaluate(
            mining_net_usd_micro=1_000_000,
            inference_net_usd_micro=2_000_000,
            feeds_ok=True,
            now_seconds=180,
        )
        self.assertTrue(decision["switched"])
        self.assertEqual(decision["mode_after"], MODE_INFERENCE)

    def test_streak_resets_when_advantage_disappears(self) -> None:
        engine = _engine(min_dwell_seconds=0)
        engine.evaluate(mining_net_usd_micro=1_000_000, inference_net_usd_micro=2_000_000, feeds_ok=True, now_seconds=0)
        engine.evaluate(mining_net_usd_micro=1_000_000, inference_net_usd_micro=2_000_000, feeds_ok=True, now_seconds=60)
        # advantage vanishes for one evaluation
        held = engine.evaluate(mining_net_usd_micro=1_000_000, inference_net_usd_micro=900_000, feeds_ok=True, now_seconds=120)
        self.assertEqual(held["reason"], "incumbent_holds")
        third = engine.evaluate(mining_net_usd_micro=1_000_000, inference_net_usd_micro=2_000_000, feeds_ok=True, now_seconds=180)
        self.assertFalse(third["switched"])  # streak restarted at 1

    def test_margin_prevents_flapping_on_oscillation(self) -> None:
        engine = _engine(min_dwell_seconds=0, consecutive_decisions=1, margin_percent=15)
        # inference oscillates within +-15% of mining: never switch
        for step, inference_net in enumerate([1_050_000, 1_100_000, 990_000, 1_140_000, 1_010_000]):
            decision = engine.evaluate(
                mining_net_usd_micro=1_000_000,
                inference_net_usd_micro=inference_net,
                feeds_ok=True,
                now_seconds=step * 60,
            )
            self.assertFalse(decision["switched"], f"flapped at step {step}")
        self.assertEqual(engine.mode, MODE_MINING)

    def test_margin_floor_applies_when_incumbent_near_zero(self) -> None:
        engine = _engine(min_dwell_seconds=0, consecutive_decisions=1, margin_floor_usd_micro=50_000)
        decision = engine.evaluate(
            mining_net_usd_micro=0,
            inference_net_usd_micro=40_000,
            feeds_ok=True,
            now_seconds=0,
        )
        self.assertFalse(decision["switched"])
        decision = engine.evaluate(
            mining_net_usd_micro=0,
            inference_net_usd_micro=60_000,
            feeds_ok=True,
            now_seconds=60,
        )
        self.assertTrue(decision["switched"])

    def test_dwell_time_blocks_rapid_switch_back(self) -> None:
        engine = _engine(consecutive_decisions=1, min_dwell_seconds=1800)
        first = engine.evaluate(
            mining_net_usd_micro=1_000_000, inference_net_usd_micro=5_000_000, feeds_ok=True, now_seconds=0
        )
        self.assertTrue(first["switched"])
        # mining now looks better, but dwell has not elapsed
        blocked = engine.evaluate(
            mining_net_usd_micro=5_000_000, inference_net_usd_micro=1_000_000, feeds_ok=True, now_seconds=600
        )
        self.assertFalse(blocked["switched"])
        self.assertEqual(blocked["reason"], "dwell_time_not_elapsed")
        self.assertEqual(engine.mode, MODE_INFERENCE)
        allowed = engine.evaluate(
            mining_net_usd_micro=5_000_000, inference_net_usd_micro=1_000_000, feeds_ok=True, now_seconds=1801
        )
        self.assertTrue(allowed["switched"])
        self.assertEqual(engine.mode, MODE_MINING)

    def test_feed_failure_always_defaults_to_mining(self) -> None:
        engine = _engine(consecutive_decisions=1, min_dwell_seconds=0)
        engine.evaluate(mining_net_usd_micro=0, inference_net_usd_micro=9_000_000, feeds_ok=True, now_seconds=0)
        self.assertEqual(engine.mode, MODE_INFERENCE)
        decision = engine.evaluate(
            mining_net_usd_micro=0, inference_net_usd_micro=9_000_000, feeds_ok=False, now_seconds=60
        )
        self.assertTrue(decision["switched"])
        self.assertEqual(decision["mode_after"], MODE_MINING)
        self.assertEqual(decision["reason"], "feed_failure_default_to_mining")
        # and it stays in mining while feeds are down, even mid-dwell
        again = engine.evaluate(
            mining_net_usd_micro=0, inference_net_usd_micro=9_000_000, feeds_ok=False, now_seconds=120
        )
        self.assertFalse(again["switched"])
        self.assertEqual(engine.mode, MODE_MINING)

    # ---- feeds ------------------------------------------------------------

    def test_json_path_and_difficulty_parsing(self) -> None:
        data = {"result": {"woHeader": {"difficulty": "0x1bc16d674ec80000"}}, "list": [{"v": 7}]}
        self.assertEqual(json_path(data, "result.woHeader.difficulty"), "0x1bc16d674ec80000")
        self.assertEqual(json_path({"list": [{"v": 7}]}, "list.0.v"), 7)
        self.assertEqual(parse_difficulty("0x10"), 16)
        self.assertEqual(parse_difficulty("1000000"), 1_000_000)
        self.assertEqual(parse_difficulty(2_500_000), 2_500_000)

    def test_gather_economics_feed_failure_and_rate_fallback(self) -> None:
        config = {
            "power": {"usd_per_kwh": "0.12"},
            "mining": {
                "fallback_hashrate_hps": 45_000_000,
                "block_reward_qi": "3",
                "price_feed": {"url": "http://example.invalid/price"},
                "difficulty_feed": {"url": "http://example.invalid/difficulty"},
            },
            "inference": {
                "fallback_usd_per_hour": "0.20",
                "utilization_percent": 50,
                "market_rate_feed": {"url": ""},
            },
        }

        def fake_fetch(feed_cfg, timeout_seconds=10.0):
            url = str(feed_cfg.get("url", "") or "")
            if "price" in url:
                return 0.10, True, ""
            return None, False, "boom"

        with mock.patch.object(crossover, "fetch_feed", side_effect=fake_fetch):
            economics = gather_economics(config, watts=300)

        self.assertFalse(economics["feeds_ok"])  # difficulty feed failed
        # inference still priced from the config fallback rate
        self.assertEqual(economics["details"]["inference_rate_source"], "config_fallback")
        self.assertEqual(
            economics["inference_net_usd_micro_per_day"],
            2_400_000 - 864_000,
        )

    def test_gather_economics_with_healthy_feeds(self) -> None:
        config = {
            "power": {"usd_per_kwh": "0.12"},
            "mining": {
                "fallback_hashrate_hps": 45_000_000,
                "block_reward_qi": "3",
                "price_feed": {"url": "http://example.invalid/price"},
                "difficulty_feed": {"url": "http://example.invalid/difficulty"},
            },
            "inference": {
                "fallback_usd_per_hour": "0.20",
                "utilization_percent": 50,
                "market_rate_feed": {"url": "http://example.invalid/rate"},
            },
        }

        def fake_fetch(feed_cfg, timeout_seconds=10.0):
            url = str(feed_cfg.get("url", "") or "")
            if "price" in url:
                return 0.10, True, ""
            if "difficulty" in url:
                return "0xe8d4a51000", True, ""  # 1e12
            return 0.25, True, ""

        with mock.patch.object(crossover, "fetch_feed", side_effect=fake_fetch):
            economics = gather_economics(config, watts=300)

        self.assertTrue(economics["feeds_ok"])
        self.assertEqual(economics["mining_net_usd_micro_per_day"], 1_166_400 - 864_000)
        self.assertEqual(economics["details"]["inference_rate_source"], "feed")
        self.assertEqual(economics["inference_net_usd_micro_per_day"], 3_000_000 - 864_000)

    # ---- sqlite log -------------------------------------------------------

    def test_db_uses_wal_and_idempotent_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = CrossoverDB(str(Path(tmp) / "crossover.db"))
            mode = db.conn.execute("PRAGMA journal_mode").fetchone()[0]
            self.assertEqual(mode.lower(), "wal")
            row = {
                "decision_id": "fixed-id",
                "ts": "2026-06-10T00:00:00+00:00",
                "mode_before": MODE_MINING,
                "mode_after": MODE_MINING,
                "switched": False,
                "reason": "incumbent_holds",
                "mining_net_usd_micro_per_day": 1,
                "inference_net_usd_micro_per_day": 2,
                "power_cost_usd_micro_per_day": 3,
                "feeds_ok": True,
                "details": {},
            }
            db.record_decision(row)
            db.record_decision(row)  # idempotent: same primary key, one row
            self.assertEqual(len(db.decisions()), 1)
            db.close()

    def test_report_daily_revenue_integration(self) -> None:
        decisions = [
            {
                "ts": "2026-06-10T00:00:00+00:00",
                "mode_after": MODE_MINING,
                "mining_net_usd_micro_per_day": 864_000,
                "inference_net_usd_micro_per_day": 2_000_000,
            },
            {
                "ts": "2026-06-10T00:01:00+00:00",
                "mode_after": MODE_INFERENCE,
                "mining_net_usd_micro_per_day": 864_000,
                "inference_net_usd_micro_per_day": 2_000_000,
            },
            # 2-hour gap: capped at max_gap_seconds, the daemon was down
            {
                "ts": "2026-06-10T02:01:00+00:00",
                "mode_after": MODE_INFERENCE,
                "mining_net_usd_micro_per_day": 864_000,
                "inference_net_usd_micro_per_day": 2_000_000,
            },
        ]

        days = report.daily_revenue(decisions, max_gap_seconds=600)

        bucket = days["2026-06-10"]
        # interval 1: 60s of mining; interval 2: capped 600s of inference
        self.assertEqual(
            bucket["daemon_usd_micro"],
            864_000 * 60 // 86_400 + 2_000_000 * 600 // 86_400,
        )
        self.assertEqual(
            bucket["mining_only_usd_micro"],
            864_000 * 60 // 86_400 + 864_000 * 600 // 86_400,
        )
        self.assertEqual(bucket["seconds"], 660)
        markdown = report.render_markdown(days)
        self.assertIn("2026-06-10", markdown)
        self.assertIn("Daemon advantage", markdown)


if __name__ == "__main__":
    unittest.main()
