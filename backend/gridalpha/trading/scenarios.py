"""Joint price scenarios from marginal quantile forecasts (Gaussian copula).

Marginals: a split-normal per hour that reproduces q10/q50/q90 exactly
(skewed: upside and downside uncertainty differ, e.g. solar hours).
Dependence: AR(1) correlation rho^|i-j| between hours, estimated from
standardised backtest residuals — errors of neighbouring hours move
together, which matters for a battery that spans 2-4 hours.
"""
from __future__ import annotations

import numpy as np

Z90 = 1.2815515655446004


def ar1_cholesky(T: int, rho: float) -> np.ndarray:
    i = np.arange(T)
    cov = rho ** np.abs(i[:, None] - i[None, :])
    return np.linalg.cholesky(cov + 1e-9 * np.eye(T))


def quantile_scenarios(q10: np.ndarray, q50: np.ndarray, q90: np.ndarray, n: int = 100,
                       rho: float = 0.85, seed: int = 0) -> np.ndarray:
    q10, q50, q90 = (np.asarray(a, dtype=float) for a in (q10, q50, q90))
    T = len(q50)
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((n, T)) @ ar1_cholesky(T, rho).T
    s_lo = np.maximum(q50 - q10, 1e-3) / Z90
    s_hi = np.maximum(q90 - q50, 1e-3) / Z90
    return q50 + np.where(z < 0, z * s_lo, z * s_hi)


def estimate_rho(std_resid_by_day: list[np.ndarray]) -> float:
    """Lag-1 autocorrelation of standardised residuals, pooled over days."""
    num, den = 0.0, 0.0
    for r in std_resid_by_day:
        r = r[np.isfinite(r)]
        if len(r) < 3:
            continue
        r = r - r.mean()
        num += float((r[1:] * r[:-1]).sum())
        den += float((r * r).sum())
    return float(np.clip(num / den, 0.0, 0.98)) if den > 0 else 0.85
