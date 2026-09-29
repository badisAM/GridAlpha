"""Forecast service: next-day quantiles per model, explanations, history."""
from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Query

from ..deps import df_records, lake_cached, require_json, require_table

router = APIRouter(prefix="/forecast", tags=["forecast"])


@router.get("/latest")
@lake_cached("forecast_latest", "forecast_meta")
def latest() -> dict:
    fc = require_table("forecast_latest")
    meta = require_json("forecast_meta")
    wide = fc.pivot_table(index=["ts", "hour"], columns="model", values=["q10", "q50", "q90"])
    wide.columns = [f"{m}_{q}" for q, m in wide.columns]
    wide = wide.reset_index().sort_values("ts")
    return {**meta, "models": sorted(fc["model"].unique().tolist()), "hours": df_records(wide, 2)}


@router.get("/explain")
@lake_cached("shap_latest", "forecast_meta")
def explain() -> dict:
    shap = require_table("shap_latest").sort_values("ts")
    meta = require_json("forecast_meta")
    feats = [c for c in shap.columns if c not in ("ts", "hour")]
    return {"target_day": meta["target_day"], "features": feats,
            "hourly": df_records(shap, 2), "drivers": meta["drivers"],
            "global_importance": meta["global_importance"]}


@router.get("/history")
@lake_cached("bt_forecasts")
def history(model: str = "ensemble", days: int = Query(14, ge=1, le=365)) -> list[dict]:
    f = require_table("bt_forecasts")
    f = f[f["model"] == model]
    last = f["delivery_date"].max()
    f = f[f["delivery_date"] > last - pd.Timedelta(days=days)].sort_values("ts")
    return df_records(f[["ts", "delivery_date", "hour", "q10", "q50", "q90", "actual"]], 2)
