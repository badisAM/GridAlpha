"""Observability service: drift, data quality, latency, pipeline runs."""
from __future__ import annotations

from fastapi import APIRouter

from ...data.lake import get_lake
from ..deps import LATENCY, require_json

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/drift")
def drift() -> dict:
    return require_json("drift")


@router.get("/data-quality")
def data_quality() -> dict:
    meta = require_json("data_meta")
    return {"mode": meta.get("mode"), "requested_mode": meta.get("requested_mode"),
            "fetched_at": meta.get("fetched_at"), "sources": meta.get("sources"),
            "fallback_reason": meta.get("fallback_reason"), "last_price_ts": meta.get("last_price_ts"),
            "rows": meta.get("rows"), **meta.get("quality", {})}


@router.get("/latency")
def latency() -> dict:
    return LATENCY.stats()


@router.get("/pipeline")
def pipeline_runs(limit: int = 30) -> list[dict]:
    runs = get_lake().read_jsonl("pipeline_runs", limit)
    for r in runs:
        r.pop("traceback", None)
    return runs[::-1]
