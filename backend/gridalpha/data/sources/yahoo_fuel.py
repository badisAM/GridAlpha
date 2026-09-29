"""Dutch TTF natural-gas front-month futures (EUR/MWh) scraped from the Yahoo
Finance chart endpoint. Gas sets the marginal price in most German hours, so
the gas level is the single most important driver of the *price level*.

Optional: if Yahoo blocks the request the pipeline continues without it
(the model then relies on lagged prices for the level).
"""
from __future__ import annotations

import pandas as pd

from ...config import get_settings
from ...log import get_logger
from .base import SourceUnavailable, cached_get_json, http_client

log = get_logger("yahoo_fuel")

URL = "https://query1.finance.yahoo.com/v8/finance/chart/TTF=F"


def fetch_ttf() -> pd.Series:
    s = get_settings()
    with http_client() as client:
        client.headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        )
        data = cached_get_json(
            client,
            URL,
            {"range": "5y", "interval": "1d"},
            s.raw_dir / "yahoo" / "ttf.json",
            immutable=False,
        )
    try:
        res = data["chart"]["result"][0]
        ts = pd.to_datetime(res["timestamp"], unit="s", utc=True)
        close = res["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError) as exc:
        raise SourceUnavailable(f"unexpected Yahoo payload: {exc}") from exc
    ser = pd.Series(close, index=ts.tz_convert("Europe/Berlin").normalize(), name="ttf").dropna()
    ser = ser[~ser.index.duplicated(keep="last")]
    log.info("ttf: %d daily closes, last=%.2f", len(ser), ser.iloc[-1])
    return ser
