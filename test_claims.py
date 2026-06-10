from __future__ import annotations

import json
import math
import sqlite3
import tempfile
import unittest
from pathlib import Path

import sample_data
from benchmark import store_measurement
from claim1_peg import analyze as claim1_analyze
from claim1_peg import joules_per_qi, modeled_cost_usd_per_qi
from claim4_settlement import SettlementLedger
from fetch_data import dig, pairs_to_daily
from qi_index import qi_micro_for_tokens
from series import align_by_date, log_returns, ols, pearson, rolling_volatility


RESEARCH_CONFIG = {
    "reference_gpu": {"hashrate_hps": 45_000_000, "watts": 300},
    "network": {"block_reward_qi": "3", "usd_per_kwh": "0.12"},
    "verdict": {"min_samples": 90},
}


class SeriesStatsTest(unittest.TestCase):
    def test_log_returns_and_rolling_volatility(self) -> None:
        values = [100.0, 110.0, 99.0, 99.0]
        returns = log_returns(values)
        self.assertAlmostEqual(returns[0], math.log(1.1), places=12)
        self.assertAlmostEqual(returns[2], 0.0, places=12)
        constant = [5.0] * 40
        vol = rolling_volatility(constant, window=30)
        self.assertIsNone(vol[10])  # no value until a full window exists
        self.assertEqual(vol[35], 0.0)

    def test_pearson_and_ols_recover_known_relationship(self) -> None:
        xs = [float(i) for i in range(50)]
        ys = [2.5 * x + 1.0 for x in xs]
        self.assertAlmostEqual(pearson(xs, ys), 1.0, places=9)
        fit = ols(xs, ys)
        self.assertAlmostEqual(fit["beta"], 2.5, places=6)
        self.assertAlmostEqual(fit["alpha"], 1.0, places=6)
        self.assertAlmostEqual(fit["r_squared"], 1.0, places=6)

    def test_ols_reports_no_fit_on_unrelated_data(self) -> None:
        xs = [math.sin(i) for i in range(60)]
        ys = [float((-1) ** i) for i in range(60)]
        fit = ols(xs, ys)
        self.assertLess(fit["r_squared"], 0.2)

    def test_align_by_date_inner_joins(self) -> None:
        a = {"2026-01-01": 1.0, "2026-01-02": 2.0, "2026-01-03": 3.0}
        b = {"2026-01-02": 20.0, "2026-01-03": 30.0, "2026-01-04": 40.0}
        dates, (av, bv) = align_by_date(a, b)
        self.assertEqual(dates, ["2026-01-02", "2026-01-03"])
        self.assertEqual(av, [2.0, 3.0])
        self.assertEqual(bv, [20.0, 30.0])


class CostModelTest(unittest.TestCase):
    def test_joules_and_usd_per_qi_known_values(self) -> None:
        joules = joules_per_qi(
            difficulty=1e12, block_reward_qi=3.0, hashrate_hps=45_000_000, watts=300.0
        )
        # 1e12/3 hashes per Qi / 45e6 H/s = 7407.41 s; x300 W = 2.2222e6 J
        self.assertAlmostEqual(joules, 1e12 / 3 / 45_000_000 * 300, places=3)
        usd = modeled_cost_usd_per_qi(
            difficulty=1e12, block_reward_qi=3.0, hashrate_hps=45_000_000, watts=300.0, usd_per_kwh=0.12
        )
        self.assertAlmostEqual(usd, joules / 3_600_000.0 * 0.12, places=9)


class Claim1VerdictTest(unittest.TestCase):
    def test_energy_driven_synthetic_data_supports_thesis(self) -> None:
        series = sample_data.generate_series()
        result = claim1_analyze(
            qi_usd=series["qi_usd"],
            btc_usd=series["btc_usd"],
            difficulty=series["difficulty"],
            config=RESEARCH_CONFIG,
        )
        self.assertEqual(result["verdict"], "supports_energy_thesis")
        energy = result["returns_regression_qi_on_energy_cost"]
        btc = result["returns_regression_qi_on_btc"]
        self.assertGreater(energy["r_squared"], btc["r_squared"])
        self.assertGreater(energy["beta"], 0)

    def test_btc_driven_price_fails_thesis(self) -> None:
        series = sample_data.generate_series()
        # Qi that is pure BTC beta: the null hypothesis should win.
        btc_values = series["btc_usd"]
        base = next(iter(btc_values.values()))
        qi_as_beta = {date: 0.08 * value / base for date, value in btc_values.items()}
        result = claim1_analyze(
            qi_usd=qi_as_beta,
            btc_usd=series["btc_usd"],
            difficulty=series["difficulty"],
            config=RESEARCH_CONFIG,
        )
        self.assertEqual(result["verdict"], "energy_thesis_not_supported")

    def test_thin_data_yields_no_verdict(self) -> None:
        series = sample_data.generate_series()
        dates = sorted(series["qi_usd"])[:30]
        result = claim1_analyze(
            qi_usd={d: series["qi_usd"][d] for d in dates},
            btc_usd={d: series["btc_usd"][d] for d in dates},
            difficulty={d: series["difficulty"][d] for d in dates},
            config=RESEARCH_CONFIG,
        )
        self.assertEqual(result["verdict"], "insufficient_data")
        self.assertIn("No conclusion", result["verdict_reason"])


class FetchShapingTest(unittest.TestCase):
    def test_pairs_to_daily_collapses_to_utc_dates(self) -> None:
        pairs = [[1717200000000, 1.0], [1717243200000, 2.0], [1717286400000, 3.0]]
        series = pairs_to_daily(pairs)
        # first two timestamps fall on the same UTC date; last value wins
        self.assertEqual(series["2024-06-01"], 2.0)
        self.assertEqual(series["2024-06-02"], 3.0)

    def test_dig_traverses_dicts_and_lists(self) -> None:
        data = {"response": {"data": [{"price": 12.5}]}}
        self.assertEqual(dig(data, "response.data.0.price"), 12.5)

    def test_sample_fixtures_are_marked_synthetic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for path in sample_data.write_sample_dir(tmp):
                payload = json.loads(Path(path).read_text(encoding="utf-8"))
                self.assertTrue(payload["synthetic"], f"{path} must be marked synthetic")
                self.assertGreater(len(payload["series"]), 100)


class QiIndexTest(unittest.TestCase):
    def test_qi_micro_for_tokens_is_exact_integer(self) -> None:
        # 1M tokens x 0.5 J/token = 5e5 J; at 2.5e6 J/Qi -> 0.2 Qi -> 200000 micro
        micro = qi_micro_for_tokens(tokens=1_000_000, joules_per_token=0.5, joules_per_qi_value=2_500_000.0)
        self.assertEqual(micro, 200_000)
        self.assertEqual(qi_micro_for_tokens(tokens=1, joules_per_token=0.5, joules_per_qi_value=0.0), 0)


class SettlementTest(unittest.TestCase):
    def _ledger(self, tmp: str) -> SettlementLedger:
        ledger = SettlementLedger(str(Path(tmp) / "settlement.db"))
        ledger.ensure_account("customer", opening_micro_qi=1_000_000)
        ledger.ensure_account("worker", opening_micro_qi=0)
        return ledger

    def test_escrow_settle_refund_conserves_micro_qi(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = self._ledger(tmp)
            before = ledger.total_micro_qi()
            ledger.quote_and_escrow(
                job_id="job-1",
                customer_id="customer",
                worker_id="worker",
                prompt="p",
                tokens=1_000_000,
                joules_per_token=0.5,
                joules_per_qi_value=2_500_000.0,
            )
            ledger.record_served("job-1", served_tokens=750_000)
            settled = ledger.settle("job-1")
            self.assertEqual(settled["settled_micro_qi"], 150_000)  # 75% of 200000
            self.assertEqual(settled["refunded_micro_qi"], 50_000)
            self.assertEqual(ledger.balance("worker"), 150_000)
            self.assertEqual(ledger.balance("customer"), 850_000)
            self.assertEqual(ledger.total_micro_qi(), before)
            ledger.close()

    def test_settle_is_idempotent_no_double_pay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = self._ledger(tmp)
            ledger.quote_and_escrow(
                job_id="job-1", customer_id="customer", worker_id="worker", prompt="p",
                tokens=100, joules_per_token=0.5, joules_per_qi_value=2_500_000.0,
            )
            ledger.record_served("job-1", served_tokens=100)
            first = ledger.settle("job-1")
            second = ledger.settle("job-1")
            self.assertEqual(first["settled_micro_qi"], second["settled_micro_qi"])
            self.assertEqual(ledger.balance("worker"), first["settled_micro_qi"])
            ledger.close()

    def test_escrow_rejects_insufficient_balance_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = self._ledger(tmp)
            with self.assertRaises(ValueError):
                ledger.quote_and_escrow(
                    job_id="too-big", customer_id="customer", worker_id="worker", prompt="p",
                    tokens=100_000_000, joules_per_token=0.5, joules_per_qi_value=2_500_000.0,
                )
            ledger.quote_and_escrow(
                job_id="job-1", customer_id="customer", worker_id="worker", prompt="p",
                tokens=100, joules_per_token=0.5, joules_per_qi_value=2_500_000.0,
            )
            balance_after_first = ledger.balance("customer")
            ledger.quote_and_escrow(  # same job_id: no second escrow
                job_id="job-1", customer_id="customer", worker_id="worker", prompt="p",
                tokens=100, joules_per_token=0.5, joules_per_qi_value=2_500_000.0,
            )
            self.assertEqual(ledger.balance("customer"), balance_after_first)
            mode = ledger.conn.execute("PRAGMA journal_mode").fetchone()[0]
            self.assertEqual(mode.lower(), "wal")
            ledger.close()


class MeasurementStoreTest(unittest.TestCase):
    def test_store_measurement_idempotent_with_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "measurements.db")
            row = {
                "measurement_id": "fixed-id",
                "ts": "2026-06-10T00:00:00+00:00",
                "gpu_name": "RTX 3090",
                "gpu_count": 1,
                "driver_version": "555.0",
                "vram_total_mb": 24576.0,
                "backend": "ollama",
                "model_name": "llama3.1:8b",
                "minutes": 5.0,
                "requests": 12,
                "output_tokens": 6000,
                "tokens_per_second": 95.0,
                "avg_watts": 310.0,
                "joules_per_token": 3.26,
                "contributor": "tester",
                "notes": None,
            }
            store_measurement(db_path, row)
            store_measurement(db_path, row)
            conn = sqlite3.connect(db_path)
            count = conn.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
            stored = conn.execute("SELECT gpu_name, joules_per_token FROM measurements").fetchone()
            conn.close()
            self.assertEqual(count, 1)
            self.assertEqual(stored[0], "RTX 3090")
            self.assertAlmostEqual(stored[1], 3.26, places=6)


if __name__ == "__main__":
    unittest.main()
