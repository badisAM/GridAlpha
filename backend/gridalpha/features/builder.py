"""Feature engineering with an explicit information set.

Every feature for delivery day D must be computable at gate closure
(D-1, 12:00 Europe/Berlin):

* D-1 prices are known (published D-2 ~12:45)       -> price lags >= 1 day
* generation / load actuals are known up to ~D-1 10:00 -> lags >= 48 h
* weather for D is a *forecast*                        -> *_fc columns
* gas (TTF) last settlement known is D-2              -> ttf lag 2 days

`tests/test_features.py` enforces this by perturbing the future and
checking that no feature of day D moves.
"""
from __future__ import annotations

import warnings
from datetime import date

import holidays
import numpy as np
import pandas as pd

from ..timeutils import TZ

LAG_ACTUALS_H = 48
WEATHER = ["temp_fc", "wind100_n_fc", "rad_s_fc", "cloud_fc"]

FEATURES: list[str] = [
    # calendar
    "hour", "dow", "month", "is_offday", "is_holiday", "doy_sin", "doy_cos",
    "hour_sin", "hour_cos",
    # weather forecasts & physics
    "temp_fc", "wind100_n_fc", "rad_s_fc", "cloud_fc", "clear_sky", "wind_cf_fc",
    # fundamental proxies (the merit-order view)
    "solar_proxy", "wind_proxy", "load_proxy", "res_proxy", "ren_share_proxy",
    "res_proxy_day_mean", "res_proxy_day_min", "res_proxy_day_max", "res_proxy_rank",
    "res_proxy_delta_d1",
    # price memory
    "p_lag1d", "p_lag2d", "p_lag7d", "p_hour_mean7", "p_d1_mean", "p_d1_min",
    "p_d1_max", "p_d1_std", "p_d1_neg_h", "p_d7_mean",
    # fuels & lagged fundamentals
    "ttf_lag", "res_act_lag48",
]

TIDE_FUTURE = ["res_proxy", "solar_proxy", "wind_proxy", "load_proxy", "temp_fc",
               "cloud_fc", "clear_sky", "hour_sin", "hour_cos", "res_proxy_rank",
               "ren_share_proxy", "res_proxy_delta_d1", "wind100_n_fc", "rad_s_fc",
               "p_lag1d", "p_lag7d", "p_hour_mean7", "res_act_lag48", "is_offday"]
TIDE_STATIC_NUM = ["is_offday", "is_holiday", "doy_sin", "doy_cos", "ttf_lag",
                   "res_proxy_day_mean", "p_d1_mean", "p_d1_std"]


def clear_sky_index(idx: pd.DatetimeIndex, lat: float = 50.0, lon: float = 10.0) -> np.ndarray:
    """Deterministic clear-sky irradiance (W/m2) — known years in advance."""
    doy = idx.dayofyear.to_numpy()
    utc_hour = idx.hour.to_numpy() + 0.5
    decl = np.deg2rad(23.44) * np.sin(2 * np.pi * (284 + doy) / 365)
    ha = np.deg2rad((utc_hour + lon / 15 - 12) * 15)
    la = np.deg2rad(lat)
    sin_el = np.sin(la) * np.sin(decl) + np.cos(la) * np.cos(decl) * np.cos(ha)
    return 1000 * np.clip(sin_el, 0, None) ** 1.15 * 0.95


def _daily_hour_lookup(df: pd.DataFrame, col: str, lag_days: int) -> np.ndarray:
    """Value of `col` at the same local hour, `lag_days` delivery days earlier."""
    table = df.pivot_table(index="delivery_date", columns="hour", values=col, aggfunc="mean")
    table.index = table.index + pd.Timedelta(days=lag_days)
    stacked = table.stack(future_stack=True)
    keys = pd.MultiIndex.from_arrays([df["delivery_date"], df["hour"]])
    return stacked.reindex(keys).to_numpy()


def _map_daily(df: pd.DataFrame, daily: pd.Series, lag_days: int) -> np.ndarray:
    d = daily.copy()
    d.index = d.index + pd.Timedelta(days=lag_days)
    return d.reindex(df["delivery_date"]).to_numpy()


def build_features(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    loc = df.index.tz_convert(TZ)
    df["delivery_date"] = loc.tz_localize(None).normalize()
    df["hour"] = loc.hour
    df["dow"] = loc.dayofweek
    df["month"] = loc.month
    doy = loc.dayofyear.to_numpy()
    df["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    years = range(loc.year.min(), loc.year.max() + 1)
    de_hol = holidays.country_holidays("DE", years=years)
    hol_days = {pd.Timestamp(d) for d in de_hol}
    df["is_holiday"] = df["delivery_date"].isin(hol_days).astype(int)
    df["is_offday"] = ((df["dow"] >= 5) | (df["is_holiday"] == 1)).astype(int)

    for c in WEATHER:
        df[c] = df[c].interpolate(limit=6, limit_direction="both")
    df["clear_sky"] = clear_sky_index(df.index)
    df["wind_cf_fc"] = 1 / (1 + np.exp(-(df["wind100_n_fc"] - 9.5) / 1.8))

    # ---- fleet-capacity estimators (rolling ratio actual / weather driver) --
    L = LAG_ACTUALS_H
    win, minp = 28 * 24, 7 * 24
    sol_act = df["solar"].shift(L)
    rad_lag = df["rad_s_fc"].shift(L).where(sol_act.notna())
    k_solar = (sol_act.rolling(win, min_periods=minp).sum()
               / rad_lag.rolling(win, min_periods=minp).sum().replace(0, np.nan)).ffill()
    wind_act = (df["wind_onshore"] + df["wind_offshore"]).shift(L)
    cf_lag = df["wind_cf_fc"].shift(L).where(wind_act.notna())
    k_wind = (wind_act.rolling(win, min_periods=minp).sum()
              / cf_lag.rolling(win, min_periods=minp).sum().replace(0, np.nan)).ffill()
    df["solar_proxy"] = df["rad_s_fc"] * k_solar
    df["wind_proxy"] = df["wind_cf_fc"] * k_wind

    loads = [_daily_hour_lookup(df, "load", 7 * k) for k in range(1, 5)]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        df["load_proxy"] = np.nanmean(np.vstack(loads), axis=0)
    # holidays behave like Sundays: scale the weekday-based proxy down
    df.loc[(df["is_holiday"] == 1) & (df["dow"] < 5), "load_proxy"] *= 0.84
    df["res_proxy"] = df["load_proxy"] - df["solar_proxy"] - df["wind_proxy"]
    df["ren_share_proxy"] = (df["solar_proxy"] + df["wind_proxy"]) / df["load_proxy"]

    g = df.groupby("delivery_date")["res_proxy"]
    df["res_proxy_day_mean"] = g.transform("mean")
    df["res_proxy_day_min"] = g.transform("min")
    df["res_proxy_day_max"] = g.transform("max")
    df["res_proxy_rank"] = g.rank(pct=True)
    df["res_proxy_delta_d1"] = df["res_proxy"] - _daily_hour_lookup(df, "res_proxy", 1)

    # ---- price memory (D-1 is fully known at gate closure) -------------------
    for lag in (1, 2, 7):
        df[f"p_lag{lag}d"] = _daily_hour_lookup(df, "price", lag)
    lags = np.vstack([_daily_hour_lookup(df, "price", k) for k in range(1, 8)])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        df["p_hour_mean7"] = np.nanmean(lags, axis=0)
    daily = df.groupby("delivery_date")["price"]
    df["p_d1_mean"] = _map_daily(df, daily.mean(), 1)
    df["p_d1_min"] = _map_daily(df, daily.min(), 1)
    df["p_d1_max"] = _map_daily(df, daily.max(), 1)
    df["p_d1_std"] = _map_daily(df, daily.std(), 1)
    df["p_d1_neg_h"] = _map_daily(df, daily.apply(lambda s: float((s < 0).sum())), 1)
    df["p_d7_mean"] = _map_daily(df, daily.mean().rolling(7, min_periods=4).mean(), 1)

    # ---- fuels & lagged fundamentals ------------------------------------------
    ttf_daily = df.groupby("delivery_date")["ttf"].first()
    full_days = pd.date_range(ttf_daily.index.min(), ttf_daily.index.max(), freq="D")
    ttf_daily = ttf_daily.reindex(full_days).ffill()
    df["ttf_lag"] = _map_daily(df, ttf_daily, 2)
    df["res_act_lag48"] = (
        df["load"] - df["solar"] - df["wind_onshore"] - df["wind_offshore"]
    ).shift(L)
    return df


def training_rows(feat: pd.DataFrame, before: pd.Timestamp | date | None = None) -> pd.DataFrame:
    """Rows with a known target and a warm feature history."""
    rows = feat[feat["price"].notna() & feat["p_lag7d"].notna() & feat["res_proxy"].notna()]
    if before is not None:
        rows = rows[rows["delivery_date"] < pd.Timestamp(before)]
    return rows


def day_rows(feat: pd.DataFrame, day: pd.Timestamp | date) -> pd.DataFrame:
    return feat[feat["delivery_date"] == pd.Timestamp(day)]
