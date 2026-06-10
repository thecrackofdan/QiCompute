"""Deterministic SYNTHETIC fixtures for pipeline tests and --sample runs.

    python3 sample_data.py    # regenerate data/sample/

These series are manufactured so the pipeline can be exercised offline. Every
file is stamped "synthetic": true and every output produced from them carries
a SYNTHETIC banner. They are never evidence for or against the thesis.

The construction is intentionally transparent: the synthetic Qi price's daily
returns are dominated by the synthetic energy-cost series (exponent 0.85)
with a small BTC admixture (exponent 0.15), so a correct claim-1 pipeline
should attribute Qi mostly to energy cost on this data - that property is
what the tests assert.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path


DAYS = 200
START = date(2025, 11, 1)


def _dates() -> list[str]:
    return [(START + timedelta(days=i)).isoformat() for i in range(DAYS)]


def generate_series() -> dict[str, dict[str, float]]:
    dates = _dates()
    difficulty: dict[str, float] = {}
    btc: dict[str, float] = {}
    qi: dict[str, float] = {}
    electricity: dict[str, float] = {}
    base_difficulty = 1.0e12
    base_btc = 60_000.0
    for i, day in enumerate(dates):
        # difficulty trends up with a fast wave so energy-cost returns carry
        # real daily variance; deterministic pseudo-noise from sin
        difficulty[day] = base_difficulty * (1.0 + 0.004 * i) * (1.0 + 0.12 * math.sin(i / 3.0))
        btc[day] = base_btc * (1.0 + 0.002 * i) * (1.0 + 0.10 * math.sin(i / 7.0 + 1.0))
        electricity[day] = 0.12 * (1.0 + 0.05 * math.sin(i / 30.0))
    # modeled cost per Qi for the reference rig in research.yaml
    # (45 MH/s, 300 W, 3 Qi/block, $0.12/kWh)
    cost = {
        day: (difficulty[day] / 3.0 / 45_000_000.0) * 300.0 / 3_600_000.0 * 0.12
        for day in dates
    }
    cost_values = list(cost.values())
    btc_values = list(btc.values())
    for i, day in enumerate(dates):
        cost_factor = cost_values[i] / cost_values[0]
        btc_factor = btc_values[i] / btc_values[0]
        qi[day] = 0.08 * (cost_factor ** 0.85) * (btc_factor ** 0.15)
    volume = {
        day: 250_000.0 * (1.0 + 0.4 * math.sin(i / 11.0)) for i, day in enumerate(dates)
    }
    return {
        "qi_usd": qi,
        "btc_usd": btc,
        "difficulty": difficulty,
        "electricity_usd_per_kwh": electricity,
        "qi_volume_usd": volume,
    }


def write_sample_dir(path: str = "data/sample") -> list[str]:
    from fetch_data import write_cache

    out_dir = Path(path)
    written = []
    for name, series in generate_series().items():
        file_path = write_cache(
            out_dir, name, series, "sample_data.py (deterministic synthetic generator)", synthetic=True
        )
        written.append(str(file_path))
    return written


if __name__ == "__main__":
    for path in write_sample_dir():
        print(f"wrote {path}")
