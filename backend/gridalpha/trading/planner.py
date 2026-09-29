"""Planner service: quantile forecast + asset spec -> committed schedule."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..timeutils import TZ
from .battery import BatterySpec, optimise
from .scenarios import quantile_scenarios


def plan_day(fc: pd.DataFrame, spec: BatterySpec, risk_aversion: float = 0.0,
             alpha: float = 0.95, n_scenarios: int = 100, rho: float = 0.85,
             seed: int = 7, actual: np.ndarray | None = None) -> tuple[pd.DataFrame, dict]:
    """`fc` columns: ts, q10, q50, q90 (one delivery day, ordered by ts)."""
    fc = fc.sort_values("ts").reset_index(drop=True)
    q10, q50, q90 = (fc[c].to_numpy(dtype=float) for c in ("q10", "q50", "q90"))
    scen = quantile_scenarios(q10, q50, q90, n=n_scenarios, rho=rho, seed=seed)
    res = optimise(spec, q50, scen, risk_aversion=risk_aversion, alpha=alpha)
    plan = pd.DataFrame({
        "ts": fc["ts"],
        "hour": pd.DatetimeIndex(fc["ts"]).tz_convert(TZ).hour,
        "q10": q10, "q50": q50, "q90": q90,
        "charge": res.charge.round(4), "discharge": res.discharge.round(4),
        "net": res.net.round(4), "soc": res.soc.round(4),
    })
    meta = {
        "expected_pnl": float(np.mean(res.scenario_pnl)) if res.scenario_pnl is not None else res.expected_pnl,
        "pnl_at_median": res.expected_pnl if risk_aversion == 0 else None,
        "risk": res.risk(alpha),
        "cycles": float(res.discharge.sum() / spec.energy_mwh),
        "energy_bought_mwh": float(res.charge.sum()),
        "energy_sold_mwh": float(res.discharge.sum()),
        "solve_ms": round(res.solve_ms, 2),
        "status": res.status,
        "risk_aversion": risk_aversion,
        "battery": spec.as_dict(),
        "scenario_pnl_hist": _hist(res.scenario_pnl),
    }
    if actual is not None and np.isfinite(actual).all():
        from .battery import settle

        plan["actual"] = actual
        oracle = optimise(spec, actual)
        meta["realised_pnl"] = settle(actual, res.charge, res.discharge, spec)
        meta["oracle_pnl"] = oracle.expected_pnl
        meta["capture_ratio"] = (meta["realised_pnl"] / oracle.expected_pnl
                                 if oracle.expected_pnl > 0 else None)
    return plan, meta


def risk_frontier(fc: pd.DataFrame, spec: BatterySpec, alpha: float = 0.95,
                  rho: float = 0.85, n_scenarios: int = 100) -> list[dict]:
    out = []
    for lam in (0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9):
        _, m = plan_day(fc, spec, lam, alpha, n_scenarios, rho)
        out.append({"risk_aversion": lam, "expected_pnl": round(m["expected_pnl"], 1),
                    "cvar": round(m["risk"].get("cvar", 0.0), 1), "cycles": round(m["cycles"], 3)})
    return out


def _hist(x: np.ndarray | None, bins: int = 20) -> list[dict]:
    if x is None or len(x) == 0:
        return []
    counts, edges = np.histogram(x, bins=bins)
    return [{"lo": round(float(a), 1), "hi": round(float(b), 1), "count": int(c)}
            for a, b, c in zip(edges[:-1], edges[1:], counts)]
