"""Scraper robustness: an unpublished open period (HTTP 404 'no content')
must be skipped, not abort the ingest."""
from datetime import date

import httpx
import pandas as pd

from gridalpha.data.sources import base, energy_charts


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_open_period_404_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(base, "MIN_INTERVAL_S", 0)
    client = _client(lambda req: httpx.Response(404, text="no content"))
    out = base.cached_get_json(client, "https://x/price", {}, tmp_path / "p.json", immutable=False)
    assert out == {}
    assert not (tmp_path / "p.json").exists()


def test_closed_period_404_still_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(base, "MIN_INTERVAL_S", 0)
    client = _client(lambda req: httpx.Response(404, text="no content"))
    try:
        base.cached_get_json(client, "https://x/price", {}, tmp_path / "p.json", immutable=True)
    except base.SourceUnavailable:
        return
    raise AssertionError("a 404 on a closed month must raise")


def test_month_boundary_prices(tmp_path, monkeypatch):
    """30 Sep before publication: the September chunk has data, the 1-Oct
    chunk returns 404 -> prices for September only, no exception."""
    monkeypatch.setattr(base, "MIN_INTERVAL_S", 0)
    monkeypatch.setenv("GRIDALPHA_DATA_DIR", str(tmp_path))
    from gridalpha.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setattr(energy_charts, "today_local", lambda: date(2026, 9, 30))
    t0 = int(pd.Timestamp("2026-09-01", tz="UTC").timestamp())

    def handler(req):
        if req.url.params["start"].startswith("2026-10"):
            return httpx.Response(404, text="no content")
        return httpx.Response(200, json={"unix_seconds": [t0, t0 + 900], "price": [50.0, 70.0]})

    real = base.http_client
    monkeypatch.setattr(energy_charts, "http_client", lambda: _client(handler))
    try:
        s = energy_charts.fetch_prices(date(2026, 9, 1), date(2026, 10, 1))
    finally:
        monkeypatch.setattr(energy_charts, "http_client", real)
        get_settings.cache_clear()
    assert len(s) == 1 and s.iloc[0] == 60.0