"""Backtest service: walk-forward P&L, equity curves, day replays."""
from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, HTTPException

from ..deps import df_records, lake_cached, require_json, require_table

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.get("/summary")
@lake_cached("bt_summary")
def summary() -> dict:
    return require_json("bt_summary")


@router.get("/equity")
@lake_cached("bt_daily")
def equity() -> list[dict]:
    d = require_table("bt_daily")
    wide = d.pivot_table(index="delivery_date", columns="strategy", values="pnl").sort_index()
    cum = wide.cumsum().reset_index()
    return df_records(cum, 0)


@router.get("/daily")
@lake_cached("bt_daily")
def daily() -> list[dict]:
    d = require_table("bt_daily")
    wide = d.pivot_table(index="delivery_date", columns="strategy", values="pnl").sort_index()
    return df_records(wide.reset_index(), 0)


@router.get("/monthly")
@lake_cached("bt_daily")
def monthly() -> list[dict]:
    d = require_table("bt_daily").copy()
    d["month"] = pd.to_datetime(d["delivery_date"]).dt.strftime("%Y-%m")
    m = d.pivot_table(index="month", columns="strategy", values="pnl", aggfunc="sum")
    if "oracle" in m:
        for c in m.columns:
            if c != "oracle":
                m[f"{c}_capture"] = (m[c] / m["oracle"]).round(4)
    return df_records(m.reset_index(), 4)


@router.get("/weights")
@lake_cached("bt_weights")
def weights() -> list[dict]:
    return df_records(require_table("bt_weights"), 4)


@router.get("/days")
@lake_cached("bt_daily")
def days() -> list[str]:
    d = require_table("bt_daily")
    return [str(x.date()) for x in sorted(d["delivery_date"].unique())]


@router.get("/day/{day}")
@lake_cached("bt_dispatch", "bt_forecasts", "bt_daily")
def day(day: str) -> dict:
    ts = pd.Timestamp(day)
    disp = require_table("bt_dispatch")
    disp = disp[disp["delivery_date"] == ts]
    if disp.empty:
        raise HTTPException(404, f"{day} not in backtest window")
    fc = require_table("bt_forecasts")
    fc = fc[(fc["delivery_date"] == ts) & fc["model"].isin(["ensemble", "naive_d1", "lgbm", "tide"])]
    wide_fc = fc.pivot_table(index="ts", columns="model", values=["q10", "q50", "q90"])
    wide_fc.columns = [f"{m}_{q}" for q, m in wide_fc.columns]
    actual = fc.groupby("ts")[["actual", "hour"]].first()
    wide_fc = wide_fc.join(actual).reset_index().sort_values("ts")
    net = disp.assign(net=disp["discharge"] - disp["charge"]).pivot_table(
        index="ts", columns="strategy", values="net")
    net.columns = [f"net_{c}" for c in net.columns]
    soc = disp.pivot_table(index="ts", columns="strategy", values="soc")
    soc.columns = [f"soc_{c}" for c in soc.columns]
    sched = net.join(soc).reset_index().sort_values("ts")
    pnl = require_table("bt_daily")
    pnl = pnl[pnl["delivery_date"] == ts][["strategy", "pnl", "expected_pnl", "cycles", "solve_ms"]]
    return {"day": day, "forecast": df_records(wide_fc, 2), "schedule": df_records(sched, 3),
            "pnl": df_records(pnl, 1)}
