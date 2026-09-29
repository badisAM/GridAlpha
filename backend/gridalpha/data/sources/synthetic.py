"""Fundamental market simulator for the German/Luxembourg day-ahead zone.

Used when the public APIs are unreachable (offline demo, CI, air-gapped
laptop). It is *not* random noise: prices emerge from a merit-order model
driven by simulated weather -> renewables -> residual load -> fuel costs,
so the forecasting problem has the same structure as the real one.

Calibrated against published 2025 DE-LU statistics (EPEX / Energy-Charts /
FfE): mean ~ 89 EUR/MWh, ~ 575 negative hours, average daily spread
~ 130 EUR/MWh, record low ~ -250 EUR/MWh (11 May 2025).
"""
from __future__ import annotations

from datetime import date, timedelta

import holidays
import numpy as np
import pandas as pd
from scipy.signal import lfilter

from ...timeutils import TZ, hourly_utc_range

MUST_RUN_GW = 6.0


def _ar1(n: int, phi: float, rng: np.random.Generator, sigma: float = 1.0) -> np.ndarray:
    """Stationary AR(1) with unit (then `sigma`) marginal std, vectorised."""
    eps = rng.standard_normal(n)
    x = lfilter([np.sqrt(1 - phi**2)], [1, -phi], eps)
    return sigma * x


def _student(n: int, df: float, rng: np.random.Generator) -> np.ndarray:
    return rng.standard_t(df, n) / np.sqrt(df / (df - 2))


def simulate_market(
    start: date,
    end_weather: date,
    end_actuals: date,
    seed: int = 42,
) -> pd.DataFrame:
    """Return an hourly UTC frame with the same schema as the live ingestion.

    Columns: price, load, solar, wind_onshore, wind_offshore (actuals, up to
    `end_actuals`), temp_fc, wind100_n_fc, rad_s_fc, cloud_fc (weather
    forecasts, up to `end_weather`) and ttf (gas, EUR/MWh, business days).
    """
    rng = np.random.default_rng(seed)
    idx = hourly_utc_range(start, end_weather)
    n = len(idx)
    loc = idx.tz_convert(TZ)
    hour = loc.hour.to_numpy()
    dow = loc.dayofweek.to_numpy()
    doy = loc.dayofyear.to_numpy()
    years = ((idx - idx[0]).total_seconds() / (365.25 * 86400)).to_numpy()
    season = np.cos(2 * np.pi * (doy - 20) / 365.25)  # +1 mid-Jan, -1 mid-Jul

    de_hol = holidays.country_holidays("DE", years=range(start.year, end_weather.year + 1))
    ldates = pd.Index(loc.date)
    is_hol = np.array([d in de_hol for d in ldates])
    offday = (dow >= 5) | is_hol
    sunday_like = (dow == 6) | is_hol

    # ---------------- weather (truth) ---------------------------------------
    temp_anom = _ar1(n, 0.995, rng, 3.3)
    diurnal_amp = 3.6 - 1.6 * season
    temp = 9.8 - 9.2 * season + diurnal_amp * np.cos(2 * np.pi * (hour - 15) / 24) + temp_anom

    wind_lat = _ar1(n, 0.985, rng)
    wind_mu = 7.4 + 1.4 * np.cos(2 * np.pi * (doy - 15) / 365.25)
    wind100 = np.clip(wind_mu * np.exp(0.48 * wind_lat - 0.5 * 0.48**2), 0.2, 32)

    cloud_lat = _ar1(n, 0.97, rng)
    cloud = 1 / (1 + np.exp(-(0.35 + 1.7 * cloud_lat + 0.7 * season)))

    lat, lon = np.deg2rad(49.8), 10.0
    utc_hour = idx.hour.to_numpy() + 0.5
    decl = np.deg2rad(23.44) * np.sin(2 * np.pi * (284 + doy) / 365)
    ha = np.deg2rad((utc_hour + lon / 15 - 12) * 15)
    sin_el = np.sin(lat) * np.sin(decl) + np.cos(lat) * np.cos(decl) * np.cos(ha)
    ghi_clear = 1000 * np.clip(sin_el, 0, None) ** 1.15 * 0.95
    rad = ghi_clear * (1 - 0.74 * cloud**2.4)

    # ---------------- weather forecasts (what a trader sees at D-1) --------
    temp_fc = temp + _ar1(n, 0.9, rng, 1.0)
    wind_fc = np.clip(wind100 * np.exp(_ar1(n, 0.95, rng, 0.11)), 0.2, 32)
    cloud_fc = np.clip(cloud + _ar1(n, 0.93, rng, 0.10), 0, 1)
    rad_fc = ghi_clear * (1 - 0.74 * cloud_fc**2.4)

    # ---------------- fleet capacities (GW) ----------------------------------
    y0 = start.year - 2023 + (start.timetuple().tm_yday / 365.25)
    yrs = years + y0
    pv_cap = 67 + 16.0 * yrs
    on_cap = 58 + 2.6 * yrs
    off_cap = 8.1 + 0.5 * yrs

    solar = pv_cap * 0.56 * rad / 1000
    cf_on = 0.9 / (1 + np.exp(-(wind100 - 10.4) / 1.75))
    cf_off = 0.95 / (1 + np.exp(-(wind100 * 1.15 - 9.6) / 1.5))
    wind_on = on_cap * cf_on * np.clip(1 + _ar1(n, 0.9, rng, 0.05), 0.5, 1.5)
    wind_off = off_cap * cf_off

    # ---------------- demand -------------------------------------------------
    weekday_shape = np.array(
        [0.80, 0.78, 0.77, 0.77, 0.79, 0.84, 0.93, 1.01, 1.05, 1.06, 1.07, 1.07,
         1.06, 1.05, 1.04, 1.03, 1.03, 1.05, 1.06, 1.04, 0.99, 0.94, 0.89, 0.84]
    )
    offday_shape = np.array(
        [0.84, 0.81, 0.79, 0.78, 0.78, 0.79, 0.81, 0.85, 0.90, 0.94, 0.97, 0.98,
         0.97, 0.95, 0.93, 0.92, 0.93, 0.96, 0.99, 0.99, 0.96, 0.93, 0.90, 0.87]
    )
    shape = np.where(offday, offday_shape[hour], weekday_shape[hour])
    level = np.where(sunday_like, 0.83, np.where(dow == 5, 0.9, 1.0))
    base = 55.0 * (1 + 0.06 * season)
    heat = 0.38 * np.clip(14 - temp, 0, None)
    cool = 0.25 * np.clip(temp - 24, 0, None)
    load = base * shape * level + heat + cool + _ar1(n, 0.95, rng, 1.1)

    residual = load - solar - wind_on - wind_off - MUST_RUN_GW  # GW

    # ---------------- fuels ----------------------------------------------------
    days = pd.date_range(start, end_weather, freq="D")
    nd = len(days)
    # fuel paths are anchored on absolute calendar time (not on `start`) so any
    # history window reproduces the same market regime
    dy = ((days - pd.Timestamp("2023-01-01")).days / 365.25).to_numpy()
    ttf_target = np.log(36) + (np.log(55) - np.log(36)) * np.exp(-np.clip(dy, 0, None) / 0.2) \
        + 0.12 * np.cos(2 * np.pi * (days.dayofyear.to_numpy() - 20) / 365.25)
    ttf_log = np.empty(nd)
    ttf_log[0] = ttf_target[0] + 0.05
    shocks = rng.standard_normal(nd) * 0.028
    for i in range(1, nd):
        ttf_log[i] = ttf_log[i - 1] + 0.04 * (ttf_target[i] - ttf_log[i - 1]) + shocks[i]
    ttf_daily = pd.Series(np.exp(ttf_log), index=days.date)
    eua_daily = pd.Series(
        np.interp(dy, [0, 1.0, 2.0, 3.0, 4.0], [84, 66, 71, 76, 78])
        + _ar1(nd, 0.97, rng, 3.0),
        index=days.date,
    )
    ttf_h = ttf_daily.reindex(ldates).to_numpy()
    eua_h = eua_daily.reindex(ldates).to_numpy()
    mc_gas = ttf_h / 0.55 + 0.37 * eua_h
    mc_peak = ttf_h / 0.38 + 0.55 * eua_h

    # ---------------- merit order ---------------------------------------------
    R = residual
    # exports / flexible demand absorb surplus: prices only turn negative
    # once residual load drops below ~ -13 GW
    k_R = np.array([-13.0, -3.0, 6.0, 16.0, 25.0, 34.0, 43.0, 54.0])
    k_p = np.stack(
        [
            np.full(n, -0.5),
            0.10 * mc_gas,
            0.45 * mc_gas,
            0.82 * mc_gas,
            1.0 * mc_gas,
            1.3 * mc_gas,
            1.0 * mc_peak,
            1.7 * mc_peak,
        ]
    )
    # vectorised piecewise-linear interpolation with per-hour knot prices
    seg = np.clip(np.searchsorted(k_R, R, side="right") - 1, 0, len(k_R) - 2)
    x0, x1 = k_R[seg], k_R[seg + 1]
    y0_, y1_ = k_p[seg, np.arange(n)], k_p[seg + 1, np.arange(n)]
    w = np.clip((R - x0) / (x1 - x0), 0, None)
    price = y0_ + w * (y1_ - y0_)
    price = np.where(R > k_R[-1], k_p[-1] + 8.0 * (R - k_R[-1]), price)

    # oversupply regime: saturating negative prices, rare extreme events
    neg = -0.5 - 14.0 * (1 - np.exp((R - k_R[0]) / 11.0))
    price = np.where(R < k_R[0], neg, price)
    day_codes = pd.factorize(ldates)[0]
    day_min_R = pd.Series(R).groupby(day_codes).transform("min").to_numpy()
    event_draw = rng.random(day_codes.max() + 1)[day_codes]
    event_mult = rng.uniform(3, 17, day_codes.max() + 1)[day_codes]
    extreme = (R < -10) & sunday_like & (day_min_R < -24) & (event_draw < 0.22)
    price = np.where(extreme, price * event_mult, price)

    # evening ramp scarcity + market noise (daily level shocks + hourly t-noise)
    ramp = (24.0 * np.exp(-0.5 * ((hour - 19.0) / 1.7) ** 2)
            + 10.0 * np.exp(-0.5 * ((hour - 7.5) / 1.2) ** 2)) * np.where(offday, 0.5, 1.0)
    daily_shock = _ar1(day_codes.max() + 1, 0.6, rng, 6.0)[day_codes]
    scale = np.clip(np.abs(price) / 90.0, 0.15, 2.5)
    hourly = lfilter([np.sqrt(1 - 0.75**2)], [1, -0.75], _student(n, 4, rng)) * 6.5 * scale
    price = price + ramp + np.where(R > k_R[1], daily_shock, 0.25 * daily_shock) + hourly
    price = np.clip(price, -500, 4000).round(2)

    df = pd.DataFrame(
        {
            "price": price,
            "load": load * 1000,
            "solar": solar * 1000,
            "wind_onshore": wind_on * 1000,
            "wind_offshore": wind_off * 1000,
            "temp_fc": temp_fc,
            "wind100_n_fc": wind_fc,
            "rad_s_fc": rad_fc,
            "cloud_fc": cloud_fc * 100,
            "ttf": ttf_h,
        },
        index=idx.rename("ts"),
    ).round(3)

    # availability: actuals & prices only up to end_actuals; gas on business days
    cut = pd.Timestamp(end_actuals + timedelta(days=1)).tz_localize(TZ).tz_convert("UTC")
    df.loc[df.index >= cut, ["price", "load", "solar", "wind_onshore", "wind_offshore", "ttf"]] = np.nan
    df.loc[pd.Index(loc.dayofweek) >= 5, "ttf"] = np.nan
    return df
