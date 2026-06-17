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
    eth: dict[str, float] = {}
    qi: dict[str, float] = {}
    electricity: dict[str, float] = {}
    token_choice_qi_fraction: dict[str, float] = {}
    exchange_rate_qi_per_quai: dict[str, float] = {}
    # SOAP workshare difficulty series (synthetic)
    # kawpow_ws: KawPoW workshares below block threshold (GPU miners)
    # soap_ws: SOAP workshares (SHA-256 / Scrypt ASICs) - introduced Dec 2025
    # We model SOAP workshares as starting small and growing as ASIC miners
    # discover the merge-mining opportunity. The soap_ws difficulty is in
    # SHA-256/Scrypt units; after energy normalisation in claim1_peg.py the
    # contribution to effective difficulty is small but non-zero.
    workshare_difficulty_kawpow_ws: dict[str, float] = {}
    workshare_difficulty_soap_ws: dict[str, float] = {}
    base_difficulty = 1.0e12
    base_btc = 60_000.0
    base_eth = 3_000.0
    # Synthetic token choice: starts near 0.1 (miners prefer QUAI), drifts up
    # slowly with noise.  The exchange rate responds with a negative lag:
    # when qi_fraction is low, the rate rises (controller restores equilibrium).
    base_er = 13.26  # Qi per QUAI at 1e18 scale (observed on-chain 2026-06)
    # SOAP launched ~day 45 in our synthetic window (Dec 2025 equivalent)
    soap_launch_day = 45
    for i, day in enumerate(dates):
        # difficulty trends up with a fast wave so energy-cost returns carry
        # real daily variance; deterministic pseudo-noise from sin
        difficulty[day] = base_difficulty * (1.0 + 0.004 * i) * (1.0 + 0.12 * math.sin(i / 3.0))
        btc[day] = base_btc * (1.0 + 0.002 * i) * (1.0 + 0.10 * math.sin(i / 7.0 + 1.0))
        eth[day] = base_eth * (1.0 + 0.0025 * i) * (1.0 + 0.12 * math.sin(i / 6.0 + 2.0))
        electricity[day] = 0.12 * (1.0 + 0.05 * math.sin(i / 30.0))
        # Synthetic miner preference: mostly QUAI (low qi_fraction) with slow
        # oscillation; clipped to [0, 1]
        frac = 0.08 + 0.06 * math.sin(i / 20.0) + 0.02 * math.sin(i / 5.0)
        token_choice_qi_fraction[day] = max(0.0, min(1.0, frac))
        # Synthetic exchange rate: base + controller response (negatively
        # correlated with qi_fraction at lag ~3 days) + slow upward drift
        lag_frac = 0.08 + 0.06 * math.sin(max(0, i - 3) / 20.0)
        er = base_er * (1.0 + 0.002 * i) * (1.0 - 0.4 * lag_frac + 0.03 * math.sin(i / 8.0))
        exchange_rate_qi_per_quai[day] = max(1.0, er)
        # KawPoW workshares: ~3-5 per block, difficulty ~10% of block difficulty
        kw_ws = difficulty[day] * 0.10 * (3.0 + 1.5 * math.sin(i / 4.0))
        workshare_difficulty_kawpow_ws[day] = max(0.0, kw_ws)
        # SOAP workshares: zero before launch, then growing adoption curve
        # SHA-256 difficulty is ~1e8x larger than KawPoW difficulty per hash,
        # but energy_factor normalises it down; synthetic values are in
        # SHA-256 hash units (so they look large but contribute small energy)
        if i < soap_launch_day:
            workshare_difficulty_soap_ws[day] = 0.0
        else:
            days_since_launch = i - soap_launch_day
            # Logistic adoption curve: grows from 0 to ~5e19 (Bitcoin-scale SHA-256 diff)
            adoption = 1.0 / (1.0 + math.exp(-0.05 * (days_since_launch - 30)))
            soap_ws = 5.0e19 * adoption * (1.0 + 0.15 * math.sin(i / 5.0))
            workshare_difficulty_soap_ws[day] = max(0.0, soap_ws)
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
        "eth_usd": eth,
        "difficulty": difficulty,
        "electricity_usd_per_kwh": electricity,
        "qi_volume_usd": volume,
        "token_choice_qi_fraction": token_choice_qi_fraction,
        "exchange_rate_qi_per_quai": exchange_rate_qi_per_quai,
        "workshare_difficulty_kawpow_ws": workshare_difficulty_kawpow_ws,
        "workshare_difficulty_soap_ws": workshare_difficulty_soap_ws,
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
