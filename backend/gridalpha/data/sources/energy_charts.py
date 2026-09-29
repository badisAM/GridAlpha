"""Energy-Charts (Fraunhofer ISE) public API — day-ahead prices and power
generation/load for Germany. No API key; data licensed CC BY 4.0
(Bundesnetzagentur | SMARD.de).

Since 1 Oct 2025 the SDAC day-ahead market clears in 15-minute MTUs; we
aggregate everything to hourly means (see docs/ARCHITECTURE.md, ADR-004).
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from ...config import get_settings
from ...log import get_logger
from ...timeutils import today_local
from .base import cached_get_json, http_client, month_chunks

log = get_logger("energy_charts")

BASE = "https://api.energy-charts.info"

POWER_COLUMNS = {
    "Load": "load",
    "Solar": "solar",
    "Wind onshore": "wind_onshore",
    "Wind offshore": "wind_offshore",
}


def _to_hourly(unix: list[int], values: list[float | None], name: str) -> pd.Series:
    s = pd.Series(
        np.asarray(values, dtype="float64"),
        index=pd.to_datetime(np.asarray(unix, dtype="int64"), unit="s", utc=True),
        name=name,
    )
    s = s[~s.index.duplicated()]
    return s.resample("h").mean()


def fetch_prices(start: date, end: date) -> pd.Series:
    s = get_settings()
    parts = []
    with http_client() as client:
        for a, b in month_chunks(start, end):
            immutable = b < today_local().replace(day=1)
            data = cached_get_json(
                client,
                f"{BASE}/price",
                {"bzn": s.bidding_zone, "start": a.isoformat(), "end": b.isoformat()},
                s.raw_dir / "energy_charts" / f"price_{s.bidding_zone}_{a:%Y-%m}.json",
                immutable,
            )
            if data.get("unix_seconds"):
                parts.append(_to_hourly(data["unix_seconds"], data["price"], "price"))
    out = pd.concat(parts).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    log.info("prices: %d hourly rows (%s -> %s)", len(out), out.index.min(), out.index.max())
    return out


def fetch_power(start: date, end: date) -> pd.DataFrame:
    s = get_settings()
    frames = []
    with http_client() as client:
        for a, b in month_chunks(start, end):
            immutable = b < today_local().replace(day=1)
            data = cached_get_json(
                client,
                f"{BASE}/public_power",
                {"country": s.country, "start": a.isoformat(), "end": b.isoformat()},
                s.raw_dir / "energy_charts" / f"power_{s.country}_{a:%Y-%m}.json",
                immutable,
            )
            unix = data.get("unix_seconds") or []
            if not unix:
                continue
            cols = {}
            for pt in data.get("production_types", []):
                key = POWER_COLUMNS.get(pt.get("name"))
                if key:
                    cols[key] = _to_hourly(unix, pt["data"], key)
            if cols:
                frames.append(pd.DataFrame(cols))
    out = pd.concat(frames).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    log.info("power: %d hourly rows, columns=%s", len(out), list(out.columns))
    return out
