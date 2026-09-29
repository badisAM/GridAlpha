"""Shared HTTP plumbing for the public-data scrapers: retries with
exponential back-off, a polite User-Agent and an on-disk raw cache (past
months never change, so they are fetched exactly once)."""
from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from ...config import get_settings
from ...log import get_logger

log = get_logger("sources")

USER_AGENT = "GridAlpha/1.0 (+https://github.com/badisAM; energy-trading research project)"


class SourceUnavailable(RuntimeError):
    """Raised when a remote source cannot be reached (triggers fallback)."""


# Energy-Charts rate-limits bursts (HTTP 429). We space requests out and,
# on 429, wait for the server's Retry-After (or back off exponentially).
MIN_INTERVAL_S = 1.5
MAX_ATTEMPTS = 8
_last_call = 0.0


def _get(client: httpx.Client, url: str, params: dict[str, Any]) -> Any:
    global _last_call
    delay = 2.0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        wait = MIN_INTERVAL_S - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()
        try:
            r = client.get(url, params=params)
        except httpx.TransportError:
            if attempt == MAX_ATTEMPTS:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 60)
            continue
        if r.status_code in (429, 500, 502, 503, 504) and attempt < MAX_ATTEMPTS:
            retry_after = r.headers.get("Retry-After", "")
            pause = float(retry_after) if retry_after.isdigit() else delay
            log.info("HTTP %s from %s — retrying in %.0fs (attempt %d/%d)",
                     r.status_code, url.split("/")[2], pause, attempt, MAX_ATTEMPTS)
            time.sleep(min(pause, 120))
            delay = min(delay * 2, 60)
            continue
        if r.status_code >= 400:
            raise SourceUnavailable(f"{url} -> HTTP {r.status_code}: {r.text[:200]}")
        return r.json()
    raise SourceUnavailable(f"{url}: too many retries")


def http_client() -> httpx.Client:
    s = get_settings()
    return httpx.Client(
        timeout=s.http_timeout_s,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        follow_redirects=True,
    )


def cached_get_json(
    client: httpx.Client,
    url: str,
    params: dict[str, Any],
    cache_file: Path,
    immutable: bool,
) -> Any:
    """GET json with a raw-file cache. `immutable` = the period is closed."""
    if immutable and cache_file.exists():
        return json.loads(cache_file.read_text())
    try:
        data = _get(client, url, params)
    except (httpx.HTTPError, SourceUnavailable) as exc:
        if cache_file.exists():
            log.warning("fetch failed (%s) — using stale cache %s", exc, cache_file.name)
            return json.loads(cache_file.read_text())
        raise SourceUnavailable(str(exc)) from exc
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data))
    return data


def month_chunks(start: date, end: date) -> list[tuple[date, date]]:
    """Split [start, end] into calendar-month chunks."""
    out: list[tuple[date, date]] = []
    cur = date(start.year, start.month, 1)
    while cur <= end:
        nxt = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
        out.append((max(cur, start), min(date.fromordinal(nxt.toordinal() - 1), end)))
        cur = nxt
    return out