"""Market-time helpers.

The German day-ahead auction (EPEX / SDAC) closes at 12:00 CET on D-1 for the
24 delivery hours of day D (local time). All data is stored in UTC; delivery
days and hours are always derived in Europe/Berlin so DST days (23 h / 25 h)
are handled correctly.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

TZ = "Europe/Berlin"
GATE_CLOSURE_HOUR = 12  # local time on D-1


def now_local() -> pd.Timestamp:
    return pd.Timestamp.now(tz=TZ)


def today_local() -> date:
    return now_local().date()


def delivery_index(day: date) -> pd.DatetimeIndex:
    """Hourly UTC timestamps covering the local delivery day (23/24/25 values)."""
    start = pd.Timestamp(day).tz_localize(TZ)
    end = pd.Timestamp(day + timedelta(days=1)).tz_localize(TZ)
    return pd.date_range(start, end, freq="h", inclusive="left").tz_convert("UTC")


def to_local(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return idx.tz_convert(TZ)


def delivery_dates(idx: pd.DatetimeIndex) -> pd.Index:
    """Local delivery date for each UTC timestamp (as python date objects)."""
    return pd.Index(to_local(idx).date, name="delivery_date")


def gate_closure(day: date) -> pd.Timestamp:
    """Gate-closure instant (UTC) of the auction that sets prices for `day`."""
    return (
        pd.Timestamp(datetime.combine(day - timedelta(days=1), datetime.min.time()))
        .tz_localize(TZ)
        + pd.Timedelta(hours=GATE_CLOSURE_HOUR)
    ).tz_convert("UTC")


def hourly_utc_range(start: date, end_inclusive: date) -> pd.DatetimeIndex:
    s = pd.Timestamp(start).tz_localize(TZ).tz_convert("UTC")
    e = pd.Timestamp(end_inclusive + timedelta(days=1)).tz_localize(TZ).tz_convert("UTC")
    return pd.date_range(s, e, freq="h", inclusive="left")
