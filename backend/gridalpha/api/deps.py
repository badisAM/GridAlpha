"""Serving helpers: lake-aware response cache + latency telemetry."""
from __future__ import annotations

import functools
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
from fastapi import HTTPException

from ..data.lake import get_lake

_cache: dict[tuple, Any] = {}
_cache_lock = threading.Lock()


def _stamp(table: str) -> float | None:
    lake = get_lake()
    for p in (lake.root / f"{table}.parquet", lake.root / f"{table}.json"):
        if p.exists():
            return p.stat().st_mtime
    return None


def df_records(df: pd.DataFrame, ndigits: int = 2) -> list[dict]:
    """DataFrame -> JSON-safe records (ISO timestamps, NaN -> null)."""
    out = df.copy()
    for c in out.columns:
        if isinstance(out[c].dtype, pd.DatetimeTZDtype):
            out[c] = out[c].dt.tz_convert("UTC").dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        elif pd.api.types.is_datetime64_any_dtype(out[c]):
            out[c] = out[c].dt.strftime("%Y-%m-%d")
    num = out.select_dtypes("number").columns
    out[num] = out[num].round(ndigits)
    out = out.astype(object).where(pd.notna(out), None)
    return out.to_dict("records")


def lake_cached(*tables: str) -> Callable:
    """Memoise a pure function of the lake: the cache key includes the
    mtimes of the tables it reads, so a pipeline run invalidates it for free
    (no TTL guessing, no stale data)."""

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            stamps = tuple(_stamp(t) for t in tables)
            # module + qualified name + tables: two routes may share a function
            # name (market.summary / backtest.summary) and, in a deployed snapshot,
            # every lake file has the same mtime -> the old key collided
            key = (fn.__module__, fn.__qualname__, tables, args, tuple(sorted(kwargs.items())), stamps)
            with _cache_lock:
                if key in _cache:
                    return _cache[key]
            try:
                val = fn(*args, **kwargs)
            except FileNotFoundError as exc:
                raise HTTPException(503, f"{exc} — run `python -m gridalpha.cli run --quick`") from exc
            with _cache_lock:
                if len(_cache) > 512:
                    _cache.clear()
                _cache[key] = val
            return val

        return wrapper

    return deco


def require_json(name: str) -> Any:
    obj = get_lake().read_json(name)
    if obj is None:
        raise HTTPException(503, f"'{name}' not available yet — run the pipeline first")
    return obj


def require_table(name: str):
    try:
        return get_lake().read(name)
    except FileNotFoundError as exc:
        raise HTTPException(503, f"{exc} — run `python -m gridalpha.cli run --quick`") from exc


class LatencyRecorder:
    """Ring buffer of request durations per route (p50/p95/p99)."""

    def __init__(self, maxlen: int = 2000) -> None:
        self.samples: dict[str, deque] = defaultdict(lambda: deque(maxlen=maxlen))
        self.lock = threading.Lock()

    def add(self, route: str, ms: float) -> None:
        with self.lock:
            self.samples[route].append(ms)

    def stats(self) -> dict:
        with self.lock:
            snap = {k: np.array(v) for k, v in self.samples.items() if len(v)}
        routes = []
        allv = []
        for k, v in snap.items():
            allv.append(v)
            routes.append({"route": k, "count": int(len(v)),
                           "p50_ms": round(float(np.percentile(v, 50)), 2),
                           "p95_ms": round(float(np.percentile(v, 95)), 2),
                           "p99_ms": round(float(np.percentile(v, 99)), 2)})
        routes.sort(key=lambda r: -r["p95_ms"])
        reads = [v for k, v in snap.items() if k.startswith("GET ")]
        read = ({"read_p95_ms": round(float(np.percentile(np.concatenate(reads), 95)), 2)}
                if reads else {"read_p95_ms": None})
        if allv:
            a = np.concatenate(allv)
            overall = {"count": int(len(a)), "p50_ms": round(float(np.percentile(a, 50)), 2),
                       "p95_ms": round(float(np.percentile(a, 95)), 2),
                       "p99_ms": round(float(np.percentile(a, 99)), 2)}
        else:
            overall = {"count": 0, "p50_ms": None, "p95_ms": None, "p99_ms": None}
        return {**overall, **read, "routes": routes}


LATENCY = LatencyRecorder()


class LatencyMiddleware:
    """Pure ASGI middleware (cheaper than BaseHTTPMiddleware)."""

    SKIP = ("/ws", "/docs", "/openapi.json", "/redoc")

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"].startswith(self.SKIP):
            return await self.app(scope, receive, send)
        t0 = time.perf_counter()

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                ms = (time.perf_counter() - t0) * 1000
                headers = list(message.get("headers", []))
                headers.append((b"server-timing", f"app;dur={ms:.2f}".encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route = scope.get("route")
            name = getattr(route, "path", None) or scope["path"]
            if scope["method"] != "OPTIONS":
                LATENCY.add(f"{scope['method']} {name}", (time.perf_counter() - t0) * 1000)
