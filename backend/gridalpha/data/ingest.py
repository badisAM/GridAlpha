"""Ingestion service: scrape every source, align on one hourly UTC grid,
run data-quality checks and publish the `market_hourly` table to the lake.

Fallback policy (data_mode=auto): if a *core* source (prices, power,
weather) is unreachable we switch the whole dataset to the calibrated
simulator rather than mixing real and synthetic series; optional sources
(TTF gas) degrade gracefully. The chosen mode is exposed in the API and the
UI so nobody mistakes simulated numbers for market data.
"""
from __future__ import annotations

from datetime import timedelta

import httpx
import numpy as np
import pandas as pd

from ..config import get_settings
from ..log import get_logger
from ..timeutils import TZ, hourly_utc_range, now_local, today_local
from .lake import get_lake
from .quality import run_quality_checks
from .sources.base import SourceUnavailable
from .sources.synthetic import simulate_market

log = get_logger("ingest")

CORE_COLUMNS = ["price", "load", "solar", "wind_onshore", "wind_offshore",
                "temp_fc", "wind100_n_fc", "rad_s_fc", "cloud_fc"]


def _live_frame() -> tuple[pd.DataFrame, dict]:
    from .sources import energy_charts, open_meteo, yahoo_fuel

    s = get_settings()
    today = today_local()
    start = s.history_start
    status: dict[str, str] = {}

    prices = energy_charts.fetch_prices(start, today + timedelta(days=1))
    status["energy_charts.price"] = "ok"
    power = energy_charts.fetch_power(start, today)
    status["energy_charts.public_power"] = "ok"
    weather = open_meteo.fetch_weather(start, today + timedelta(days=2))
    status["open_meteo"] = "ok"

    idx = hourly_utc_range(start, today + timedelta(days=2))
    frame = pd.DataFrame(index=idx.rename("ts"))
    frame = frame.join(prices).join(power).join(weather)

    try:
        ttf = yahoo_fuel.fetch_ttf()
        local_days = pd.Index(frame.index.tz_convert(TZ).normalize())
        frame["ttf"] = ttf.reindex(local_days).to_numpy()
        status["yahoo.ttf"] = "ok"
    except (SourceUnavailable, httpx.HTTPError) as exc:
        log.warning("TTF gas unavailable (%s) — continuing without it", exc)
        frame["ttf"] = np.nan
        status["yahoo.ttf"] = f"unavailable: {exc}"[:160]
    return frame, status


def _synthetic_frame() -> tuple[pd.DataFrame, dict]:
    s = get_settings()
    today = today_local()
    frame = simulate_market(
        s.history_start, today + timedelta(days=2), today, seed=s.seed
    )
    return frame, {"simulator": "ok"}


def ingest(mode: str | None = None) -> dict:
    s = get_settings()
    mode = mode or s.data_mode
    meta: dict = {"requested_mode": mode, "fetched_at": now_local().isoformat()}

    if mode in ("auto", "live"):
        try:
            frame, status = _live_frame()
            meta.update(mode="live", sources=status)
        except (SourceUnavailable, httpx.HTTPError, OSError, KeyError, ValueError) as exc:
            if mode == "live":
                raise
            log.warning("live sources unreachable (%s) -> calibrated simulator", exc)
            frame, status = _synthetic_frame()
            meta.update(mode="synthetic", sources=status, fallback_reason=str(exc)[:300])
    else:
        frame, status = _synthetic_frame()
        meta.update(mode="synthetic", sources=status)

    frame = frame.sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    for c in CORE_COLUMNS + ["ttf"]:
        if c not in frame:
            frame[c] = np.nan
    frame = frame[CORE_COLUMNS + ["ttf"]].astype("float64")

    quality = run_quality_checks(frame)
    meta["quality"] = quality
    last_price = frame["price"].last_valid_index()
    meta["last_price_ts"] = last_price.isoformat() if last_price is not None else None
    meta["rows"] = int(len(frame))

    lake = get_lake()
    lake.write("market_hourly", frame)
    lake.write_json("data_meta", meta)
    log.info(
        "ingest done: mode=%s rows=%d quality=%s", meta["mode"], len(frame), quality["status"]
    )
    return meta
