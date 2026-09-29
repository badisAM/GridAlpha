"""Business service: BO/DSO scorecard + investment calculator."""
from __future__ import annotations

from fastapi import APIRouter

from ...backtest.report import scorecard
from ...data.lake import get_lake
from ...finance.investment import InvestmentInput, evaluate
from ..deps import LATENCY, require_json
from ..schemas import InvestmentRequest

router = APIRouter(prefix="/business", tags=["business"])


@router.get("/kpis")
def kpis() -> dict:
    summary = require_json("bt_summary")
    runs = get_lake().read_jsonl("pipeline_runs", 200)
    # DSO5 is about *read* latency: prefer the controlled benchmark
    # (scripts/benchmark.py), else the live GET-only p95 of this process.
    from ...backtest.report import _benchmark_latency

    bench = _benchmark_latency()
    live = LATENCY.stats()
    lat = bench or {"p95_ms": live.get("read_p95_ms")}
    return scorecard(summary, runs, lat)


@router.post("/investment")
def investment(req: InvestmentRequest) -> dict:
    rev = req.revenue_eur_per_mw_year
    if rev is None:
        tm = require_json("bt_summary")["trading_metrics"]
        rev = (tm.get(req.strategy) or tm.get("ensemble_cvar") or {}).get("eur_per_mw_year", 0.0)
    inp = InvestmentInput(power_mw=req.power_mw, duration_h=req.duration_h,
                          capex_eur_per_kwh=req.capex_eur_per_kwh, fixed_opex_pct=req.fixed_opex_pct,
                          revenue_eur_per_mw_year=rev, revenue_decline_pct=req.revenue_decline_pct,
                          lifetime_years=req.lifetime_years, discount_rate=req.discount_rate)
    return {"inputs": inp.__dict__, **evaluate(inp)}
