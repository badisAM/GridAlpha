"""Request / response contracts (validated by Pydantic v2, documented in /docs)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BatteryParams(BaseModel):
    power_mw: float = Field(10.0, gt=0, le=1000, description="Inverter power (MW)")
    energy_mwh: float = Field(20.0, gt=0, le=8000, description="Usable energy (MWh)")
    rte: float = Field(0.88, gt=0.5, le=1.0, description="Round-trip efficiency")
    max_cycles_per_day: float = Field(1.5, gt=0, le=4)
    degradation_eur_per_mwh: float = Field(8.0, ge=0, le=100)
    soc_init_frac: float = Field(0.5, ge=0.05, le=0.95)


class OptimizeRequest(BatteryParams):
    day: str = Field("latest", description="'latest' (next delivery day) or YYYY-MM-DD in the backtest")
    risk_aversion: float = Field(0.3, ge=0, le=1, description="0 = risk-neutral, 1 = pure CVaR")
    model: Literal["ensemble", "lgbm", "tide", "naive_d1", "profile7"] = "ensemble"


class PipelineRequest(BaseModel):
    quick: bool = True
    mode: Literal["auto", "live", "synthetic"] | None = None


class InvestmentRequest(BaseModel):
    power_mw: float = Field(10.0, gt=0)
    duration_h: float = Field(2.0, gt=0, le=12)
    capex_eur_per_kwh: float = Field(250.0, gt=0)
    fixed_opex_pct: float = Field(0.02, ge=0, le=0.2)
    revenue_eur_per_mw_year: float | None = Field(None, description="default: backtested value")
    strategy: str = "ensemble_cvar"
    revenue_decline_pct: float = Field(0.02, ge=0, le=0.2)
    lifetime_years: int = Field(15, ge=1, le=40)
    discount_rate: float = Field(0.08, ge=0, le=0.5)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=500)
