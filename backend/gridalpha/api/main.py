"""GridAlpha API — FastAPI application factory.

    uvicorn gridalpha.api.main:app --port 8000      (docs at /docs)
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .. import __version__
from ..config import get_settings
from ..data.lake import get_lake
from ..log import get_logger, setup_logging
from .deps import LatencyMiddleware
from .routers import (
    backtest,
    business,
    copilot,
    forecast,
    market,
    models,
    monitoring,
    stream,
    system,
    trading,
)

log = get_logger("api")

TAGS = [
    {"name": "system", "description": "Health, configuration and pipeline orchestration"},
    {"name": "market", "description": "Scraped market data: prices & fundamentals (DE-LU)"},
    {"name": "forecast", "description": "Probabilistic day-ahead price forecasts + SHAP explanations"},
    {"name": "trading", "description": "Battery dispatch optimisation (MILP, CVaR)"},
    {"name": "backtest", "description": "Walk-forward trading backtest"},
    {"name": "models", "description": "Model registry, leaderboard, calibration"},
    {"name": "monitoring", "description": "Drift, data quality, latency, pipeline runs"},
    {"name": "copilot", "description": "Trading brief and grounded Q&A"},
    {"name": "business", "description": "BO/DSO scorecard and investment calculator"},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    s = get_settings()
    lake = get_lake()
    for t in ("market_hourly", "bt_forecasts", "bt_dispatch", "bt_daily", "forecast_latest"):
        if lake.exists(t):
            lake.read(t)  # warm the in-memory snapshot cache
    sched = None
    if s.scheduler_enabled:
        from ..scheduler import start_background

        sched = start_background()
    log.info("API ready (data mode=%s)", s.data_mode)
    yield
    if sched:
        sched.shutdown(wait=False)


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="GridAlpha API",
        version=__version__,
        description="AI copilot for battery storage trading on the German day-ahead power market: "
                    "scraping -> probabilistic forecasting (LightGBM + TiDE) -> risk-aware MILP "
                    "dispatch -> walk-forward P&L.",
        openapi_tags=TAGS,
        lifespan=lifespan,
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(CORSMiddleware, allow_origins=s.api_cors_origins, allow_credentials=False,
                       allow_methods=["*"], allow_headers=["*"])
    app.add_middleware(LatencyMiddleware)
    api = "/api/v1"
    for r in (system, market, forecast, trading, backtest, models, monitoring, copilot, business):
        app.include_router(r.router, prefix=api)
    app.include_router(stream.router)

    @app.get("/", include_in_schema=False)
    def root():
        return {"name": "GridAlpha", "docs": "/docs", "health": f"{api}/health"}

    return app


app = create_app()
