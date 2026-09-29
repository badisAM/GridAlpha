"""Market data service: prices, fundamentals, statistics."""
from __future__ import annotations

import numpy as np
import pandas as pd
from fastapi import APIRouter, Query

from ...timeutils import TZ
from ..deps import df_records, lake_cached, require_table

router = APIRouter(prefix="/market", tags=["market"])


def _market() -> pd.DataFrame:
    df = require_table("market_hourly").copy()
    loc = df.index.tz_convert(TZ)
    df["date"] = loc.tz_localize(None).normalize()
    df["hour"] = loc.hour
    return df


@lake_cached("market_hourly")
def _daily() -> pd.DataFrame:
    df = _market()
    df = df[df["price"].notna()]
    g = df.groupby("date")
    daily = pd.DataFrame({
        "mean": g["price"].mean(), "min": g["price"].min(), "max": g["price"].max(),
        "neg_hours": g["price"].apply(lambda s: int((s < 0).sum())),
        "solar_gwh": g["solar"].sum() / 1000, "wind_gwh": (g["wind_onshore"].sum() + g["wind_offshore"].sum()) / 1000,
        "load_gwh": g["load"].sum() / 1000,
    })
    daily["spread"] = daily["max"] - daily["min"]
    return daily


@router.get("/summary")
@lake_cached("market_hourly")
def summary() -> dict:
    df = _market()
    px = df[df["price"].notna()]
    last_day = px["date"].max()
    d30 = px[px["date"] > last_day - pd.Timedelta(days=30)]
    p30 = px[(px["date"] <= last_day - pd.Timedelta(days=30)) & (px["date"] > last_day - pd.Timedelta(days=60))]
    ytd = px[px["date"].dt.year == last_day.year]
    daily = _daily()
    sp30 = daily[daily.index > last_day - pd.Timedelta(days=30)]["spread"]
    sp_prev = daily[(daily.index <= last_day - pd.Timedelta(days=30)) & (daily.index > last_day - pd.Timedelta(days=60))]["spread"]

    def r(x):
        return None if x is None or not np.isfinite(x) else round(float(x), 2)

    return {
        "last_delivery_day": str(last_day.date()),
        "mean_30d": r(d30["price"].mean()), "mean_prev_30d": r(p30["price"].mean()),
        "min_30d": r(d30["price"].min()), "max_30d": r(d30["price"].max()),
        "vol_30d": r(d30["price"].std()),
        "avg_daily_spread_30d": r(sp30.mean()), "avg_daily_spread_prev_30d": r(sp_prev.mean()),
        "neg_hours_30d": int((d30["price"] < 0).sum()), "neg_hours_ytd": int((ytd["price"] < 0).sum()),
        "mean_ytd": r(ytd["price"].mean()),
        "renewable_share_30d": r(((d30["solar"] + d30["wind_onshore"] + d30["wind_offshore"]).sum()
                                  / d30["load"].sum()) * 100),
        "last_day_curve": df_records(px[px["date"] == last_day][["hour", "price"]]),
    }


@router.get("/prices")
@lake_cached("market_hourly")
def prices(days: int = Query(14, ge=1, le=120)) -> list[dict]:
    df = _market()
    last = df.loc[df["price"].notna(), "date"].max()
    win = df[(df["date"] > last - pd.Timedelta(days=days)) & (df["date"] <= last)]
    win = win.assign(wind=win["wind_onshore"] + win["wind_offshore"]).rename_axis("ts").reset_index()
    return df_records(win[["ts", "hour", "price", "load", "solar", "wind"]], 1)


@router.get("/daily")
@lake_cached("market_hourly")
def daily(days: int = Query(365, ge=7, le=2000)) -> list[dict]:
    d = _daily().tail(days).rename_axis("date").reset_index()
    return df_records(d, 2)


@router.get("/profile")
@lake_cached("market_hourly")
def profile(year: int | None = None) -> dict:
    """Average price by month x hour — the 'duck curve' heatmap."""
    df = _market()
    df = df[df["price"].notna()]
    year = year or int(df["date"].max().year)
    y = df[df["date"].dt.year == year]
    tab = y.groupby([y["date"].dt.month, "hour"])["price"].mean().unstack().round(1)
    return {"year": year, "months": [int(m) for m in tab.index],
            "matrix": [[None if not np.isfinite(v) else float(v) for v in row] for row in tab.to_numpy()]}
