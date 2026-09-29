"""Model registry & evaluation service."""
from __future__ import annotations

import numpy as np
import pandas as pd
from fastapi import APIRouter

from ...models import registry
from ..deps import lake_cached, require_json, require_table

router = APIRouter(prefix="/models", tags=["models"])

DISPLAY = ["ensemble", "lgbm", "tide", "profile7", "naive_d1", "naive_d7"]


@router.get("")
def list_models() -> dict:
    idx = registry.load_index()
    card = registry.card() or {}
    card = {k: v for k, v in card.items() if k not in ("forecast_metrics", "trading_metrics")}
    return {"champion": idx.get("champion"), "versions": idx.get("versions", [])[::-1], "champion_card": card}


@router.get("/leaderboard")
@lake_cached("bt_summary")
def leaderboard() -> list[dict]:
    s = require_json("bt_summary")
    fm, tm = s["forecast_metrics"], s["trading_metrics"]
    rows = []
    for m in DISPLAY:
        if m not in fm:
            continue
        r = {"model": m, **fm[m]}
        t = tm.get(m) or {}
        r["capture_ratio"] = t.get("capture_ratio")
        r["eur_per_mw_year"] = t.get("eur_per_mw_year")
        rows.append(r)
    return rows


@router.get("/error-by-hour")
@lake_cached("bt_forecasts")
def error_by_hour() -> list[dict]:
    f = require_table("bt_forecasts")
    f = f[f["model"].isin(DISPLAY)]
    f = f.assign(ae=(f["actual"] - f["q50"]).abs())
    t = f.pivot_table(index="hour", columns="model", values="ae", aggfunc="mean").round(2)
    return [{"hour": int(h), **{k: (None if pd.isna(v) else float(v)) for k, v in row.items()}}
            for h, row in t.iterrows()]


@router.get("/calibration")
@lake_cached("bt_forecasts")
def calibration() -> list[dict]:
    """Reliability: share of actuals below each predicted quantile."""
    f = require_table("bt_forecasts")
    out = []
    for m in DISPLAY:
        g = f[f["model"] == m]
        if g.empty:
            continue
        a = g["actual"].to_numpy()
        out.append({
            "model": m,
            "points": [{"nominal": q, "empirical": round(float(np.mean(a <= g[c].to_numpy())), 4)}
                       for q, c in ((0.1, "q10"), (0.5, "q50"), (0.9, "q90"))],
        })
    return out


@router.get("/importance")
@lake_cached("forecast_meta")
def importance() -> list[dict]:
    return require_json("forecast_meta")["global_importance"]
