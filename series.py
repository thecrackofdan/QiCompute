"""Time-series statistics for the claims, stdlib only.

Everything operates on aligned lists of floats. No smoothing is applied
anywhere; window parameters are explicit arguments so analysis choices are
visible at the call site.
"""
from __future__ import annotations

import math
from typing import Any


def log_returns(values: list[float]) -> list[float]:
    returns = []
    for previous, current in zip(values, values[1:]):
        if previous > 0 and current > 0:
            returns.append(math.log(current / previous))
        else:
            returns.append(0.0)
    return returns


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mu = mean(values)
    return math.sqrt(sum((v - mu) ** 2 for v in values) / (len(values) - 1))


def rolling_volatility(values: list[float], window: int) -> list[float | None]:
    """Rolling annualized volatility of log returns over a trailing window.

    Entries are None until a full window of returns exists: thin data is
    reported as missing, never extrapolated.
    """
    returns = log_returns(values)
    out: list[float | None] = [None] * len(values)
    for index in range(window, len(values)):
        window_returns = returns[index - window:index]
        out[index] = stdev(window_returns) * math.sqrt(365.0)
    return out


def pearson(xs: list[float], ys: list[float]) -> float:
    n = min(len(xs), len(ys))
    if n < 2:
        return 0.0
    xs, ys = xs[:n], ys[:n]
    mx, my = mean(xs), mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return 0.0
    return cov / math.sqrt(vx * vy)


def ols(xs: list[float], ys: list[float]) -> dict[str, Any]:
    """Single-regressor OLS with intercept: y = alpha + beta * x.

    Returns beta, alpha, r_squared, the t-statistic of beta, and n. Used on
    log-return series so levels trends do not manufacture correlation.
    """
    n = min(len(xs), len(ys))
    if n < 3:
        return {"n": n, "beta": 0.0, "alpha": 0.0, "r_squared": 0.0, "t_beta": 0.0}
    xs, ys = xs[:n], ys[:n]
    mx, my = mean(xs), mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx <= 0:
        return {"n": n, "beta": 0.0, "alpha": my, "r_squared": 0.0, "t_beta": 0.0}
    beta = sxy / sxx
    alpha = my - beta * mx
    residuals = [y - (alpha + beta * x) for x, y in zip(xs, ys)]
    ss_res = sum(r ** 2 for r in residuals)
    ss_tot = sum((y - my) ** 2 for y in ys)
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    dof = n - 2
    sigma2 = ss_res / dof if dof > 0 else 0.0
    se_beta = math.sqrt(sigma2 / sxx) if sxx > 0 and sigma2 > 0 else 0.0
    # Perfect or near-perfect fit: sigma2 -> 0 implies infinite t-statistic.
    # Return float('inf') / float('-inf') so downstream verdict logic can
    # correctly evaluate t_beta > threshold without a false zero.
    if se_beta > 0:
        t_beta = beta / se_beta
    elif beta != 0.0:
        t_beta = math.copysign(float("inf"), beta)
    else:
        t_beta = 0.0
    return {
        "n": n,
        "beta": round(beta, 8),
        "alpha": round(alpha, 10),
        "r_squared": round(max(r_squared, 0.0), 8),
        "t_beta": round(t_beta, 6),
    }


def align_by_date(*serieses: dict[str, float]) -> tuple[list[str], list[list[float]]]:
    """Inner-join several {date: value} series on their common dates."""
    common = set(serieses[0])
    for series in serieses[1:]:
        common &= set(series)
    dates = sorted(common)
    return dates, [[series[date] for date in dates] for series in serieses]
