"""Statistics used by the backtest (REQ-F07-01/02): Wilson intervals, segment bootstrap, odds ratios."""

from __future__ import annotations

import math
from typing import Any, Callable, Sequence

import numpy as np
from statsmodels.stats.proportion import proportion_confint

SEED = 20261106
ALPHA = 0.10
BOOT = 1000


def wilson(hits: int, n: int) -> tuple[float | None, float | None]:
    if n <= 0:
        return None, None
    lo, hi = proportion_confint(hits, n, alpha=ALPHA, method="wilson")
    return float(lo), float(hi)


def rng(seed: int = SEED) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed))


def bootstrap_ratio(units: Sequence[Any], statistic: Callable[[list[Any]], float | None], seed: int = SEED,
                    reps: int = BOOT) -> tuple[float | None, float | None]:
    """Resample `units` (segments) with replacement; 5th and 95th percentiles of the statistic."""
    if not units:
        return None, None
    g = rng(seed)
    n = len(units)
    vals = []
    for _ in range(reps):
        idx = g.integers(0, n, size=n)
        v = statistic([units[i] for i in idx])
        if v is not None and math.isfinite(v):
            vals.append(v)
    if not vals:
        return None, None
    return float(np.percentile(vals, 5)), float(np.percentile(vals, 95))


def odds_ratio(y: np.ndarray, x: np.ndarray, controls: np.ndarray | None) -> float | None:
    """Odds ratio per 1 SD of x from a ridge-penalised logistic regression (stable under separation)."""
    import statsmodels.api as sm

    if len(y) < 10 or y.min() == y.max() or np.nanstd(x) == 0:
        return None
    xs = (x - np.nanmean(x)) / np.nanstd(x)
    cols = [xs]
    if controls is not None and controls.size:
        c = controls.astype(float)
        sd = c.std(axis=0)
        sd[sd == 0] = 1.0
        cols.append((c - c.mean(axis=0)) / sd)
    X = sm.add_constant(np.column_stack(cols), has_constant="add")
    try:
        model = sm.GLM(y.astype(float), X, family=sm.families.Binomial())
        res = model.fit_regularized(alpha=0.01, L1_wt=0.0, maxiter=200)
        beta = float(np.asarray(res.params)[1])
    except Exception:  # noqa: BLE001 - reported as 无数据
        return None
    return math.exp(beta)


def pct_rank(values: dict[str, float | None]) -> dict[str, float]:
    """Mid-rank percentile in [0, 1] among segments that have a value; missing → 0."""
    have = {k: v for k, v in values.items() if v is not None}
    n = len(have)
    out = {k: 0.0 for k in values}
    if n <= 1:
        for k in have:
            out[k] = 1.0
        return out
    vals = sorted(have.values())
    for k, v in have.items():
        lower = sum(1 for x in vals if x < v)
        equal = sum(1 for x in vals if x == v)
        out[k] = (lower + 0.5 * (equal - 1)) / (n - 1)
    return out
