"""Open-Meteo weather *forecasts* (not observations) for 8 German sites.

Using the Historical Forecast API for the training period is deliberate: the
model is trained on the same kind of information a trader actually has at
gate closure (a forecast), which avoids the classic look-ahead bias of
training on observed weather. Tomorrow's values come from the live
Forecast API. No API key (free for non-commercial use).
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from ...config import get_settings
from ...log import get_logger
from ...timeutils import today_local
from .base import cached_get_json, http_client

log = get_logger("open_meteo")

HIST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
LIVE_URL = "https://api.open-meteo.com/v1/forecast"
VARS = ["temperature_2m", "wind_speed_100m", "shortwave_radiation", "cloud_cover"]

# (name, lat, lon, region) — north = wind belt, south = PV belt
SITES = [
    ("hamburg", 53.55, 9.99, "north"),
    ("emden", 53.37, 7.21, "north"),
    ("rostock", 54.09, 12.10, "north"),
    ("berlin", 52.52, 13.40, "north"),
    ("frankfurt", 50.11, 8.68, "south"),
    ("leipzig", 51.34, 12.37, "south"),
    ("stuttgart", 48.78, 9.18, "south"),
    ("munich", 48.14, 11.58, "south"),
]


def _params(start: date, end: date) -> dict:
    return {
        "latitude": ",".join(str(s[1]) for s in SITES),
        "longitude": ",".join(str(s[2]) for s in SITES),
        "hourly": ",".join(VARS),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "timezone": "UTC",
        "wind_speed_unit": "ms",
    }


def _aggregate(payload: list | dict) -> pd.DataFrame:
    """Per-site hourly series -> regional aggregates used as features."""
    items = payload if isinstance(payload, list) else [payload]
    per_site = []
    for (_name, _, _, region), item in zip(SITES, items):
        h = item["hourly"]
        idx = pd.to_datetime(h["time"], utc=True)
        df = pd.DataFrame({v: np.asarray(h[v], dtype="float64") for v in VARS}, index=idx)
        df["region"] = region
        per_site.append(df)
    allsites = pd.concat(per_site)
    north = allsites[allsites.region == "north"].groupby(level=0)
    south = allsites[allsites.region == "south"].groupby(level=0)
    everything = allsites.drop(columns="region").groupby(level=0)
    out = pd.DataFrame(
        {
            "temp_fc": everything["temperature_2m"].mean(),
            "wind100_n_fc": north["wind_speed_100m"].mean(),
            "rad_s_fc": south["shortwave_radiation"].mean(),
            "cloud_fc": everything["cloud_cover"].mean(),
        }
    )
    out.index.name = "ts"
    return out


def fetch_weather(start: date, end: date) -> pd.DataFrame:
    """Historical forecasts for [start, end] + live forecast for the next days."""
    s = get_settings()
    frames = []
    today = today_local()
    with http_client() as client:
        # yearly chunks keep responses < ~10 MB
        y = start.year
        while y <= min(end, today).year:
            a = max(start, date(y, 1, 1))
            b = min(end, date(y, 12, 31), today - timedelta(days=1))
            if a <= b:
                data = cached_get_json(
                    client,
                    HIST_URL,
                    _params(a, b),
                    s.raw_dir / "open_meteo" / f"hist_{a:%Y%m%d}_{b:%Y%m%d}.json",
                    immutable=b < today - timedelta(days=7),
                )
                frames.append(_aggregate(data))
            y += 1
        live = cached_get_json(
            client,
            LIVE_URL,
            {**{k: v for k, v in _params(today, today).items() if not k.endswith("_date")},
             "past_days": 3, "forecast_days": 4},
            s.raw_dir / "open_meteo" / "live.json",
            immutable=False,
        )
        frames.append(_aggregate(live))
    out = pd.concat(frames).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    log.info("weather: %d rows (%s -> %s)", len(out), out.index.min(), out.index.max())
    return out
