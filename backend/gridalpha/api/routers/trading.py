"""Trading service: committed plan, on-demand optimisation, risk frontier."""
from __future__ import annotations

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from ...config import get_settings
from ...models.base import QCOLS
from ...trading.battery import BatterySpec
from ...trading.planner import plan_day, risk_frontier
from ..deps import df_records, lake_cached, require_json, require_table
from ..schemas import OptimizeRequest

router = APIRouter(prefix="/trading", tags=["trading"])


@router.get("/plan")
@lake_cached("plan_latest", "plan_meta")
def plan() -> dict:
    p = require_table("plan_latest").sort_values("ts")
    return {**require_json("plan_meta"), "schedule": df_records(p, 3)}


def _forecast_for(day: str, model: str) -> tuple[pd.DataFrame, np.ndarray | None, str]:
    if day == "latest":
        fc = require_table("forecast_latest")
        fc = fc[fc["model"] == model].sort_values("ts")
        if fc.empty:
            raise HTTPException(404, f"model '{model}' has no latest forecast")
        return fc[["ts", *QCOLS]], None, require_json("forecast_meta")["target_day"]
    bt = require_table("bt_forecasts")
    d = pd.Timestamp(day)
    f = bt[(bt["model"] == model) & (bt["delivery_date"] == d)].sort_values("ts")
    if f.empty:
        raise HTTPException(404, f"no backtest forecast for {day} (model {model})")
    return f[["ts", *QCOLS]], f["actual"].to_numpy(dtype=float), day


def _spec(req: OptimizeRequest) -> BatterySpec:
    return BatterySpec(power_mw=req.power_mw, energy_mwh=req.energy_mwh, rte=req.rte,
                       max_cycles_per_day=req.max_cycles_per_day,
                       degradation_eur_per_mwh=req.degradation_eur_per_mwh,
                       soc_init_frac=req.soc_init_frac)


@router.post("/optimize")
async def optimize(req: OptimizeRequest) -> dict:
    """Re-optimise any day for any battery / risk appetite (MILP, ~20-60 ms)."""
    fc, actual, day = _forecast_for(req.day, req.model)
    s = get_settings()
    rho = float((require_json("bt_summary") or {}).get("copula_rho", 0.85))
    plan_df, meta = await run_in_threadpool(
        plan_day, fc, _spec(req), req.risk_aversion, s.cvar_alpha, s.n_scenarios, rho, 7, actual)
    return {**meta, "day": day, "model": req.model, "schedule": df_records(plan_df, 3)}


@router.post("/frontier")
async def frontier(req: OptimizeRequest) -> dict:
    """Expected P&L vs CVaR for a grid of risk-aversion levels."""
    fc, _, day = _forecast_for(req.day, req.model)
    rho = float((require_json("bt_summary") or {}).get("copula_rho", 0.85))
    pts = await run_in_threadpool(risk_frontier, fc, _spec(req), get_settings().cvar_alpha, rho)
    return {"day": day, "points": pts}
