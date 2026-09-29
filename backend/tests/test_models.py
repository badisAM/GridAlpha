from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gridalpha.finance.investment import InvestmentInput, evaluate
from gridalpha.models.ensemble import AdaptiveConformal, softmax_weights
from gridalpha.models.metrics import forecast_metrics, pinball
from gridalpha.monitoring.drift import psi


def test_pinball_properties():
    y = np.array([10.0, 20.0, 30.0])
    assert pinball(y, y, 0.5) == 0
    assert pinball(y, y - 10, 0.9) == pytest.approx(9.0) and pinball(y, y + 10, 0.9) == pytest.approx(1.0)


def test_metrics_perfect_forecast():
    days = pd.date_range("2025-01-01", periods=3, freq="D").repeat(24)
    a = np.tile(np.arange(24, dtype=float), 3)
    df = pd.DataFrame({"delivery_date": days, "actual": a, "q10": a - 1, "q50": a, "q90": a + 1})
    m = forecast_metrics(df)
    assert m["mae"] == 0 and m["coverage_80"] == 1 and m["kendall_tau"] == 1 and m["peak_hour_hit"] == 1


def test_ensemble_weights_prefer_better_expert():
    losses = pd.DataFrame({"good": [3.0, 3.1, 2.9], "bad": [4.0, 4.2, 3.9]})
    w = softmax_weights(losses, temperature=0.05)
    assert w["good"] > 0.95 and abs(sum(w.values()) - 1) < 1e-9
    assert softmax_weights(pd.DataFrame(columns=["a", "b"], dtype=float), 0.05) == {"a": 0.5, "b": 0.5}


def test_adaptive_conformal_restores_coverage():
    rng = np.random.default_rng(0)
    aci = AdaptiveConformal(target=0.8, gamma=0.05)
    cover = []
    for _ in range(200):
        y = pd.Series(rng.normal(0, 2.0, 24))        # true sd = 2
        q = pd.DataFrame({"q10": -1.28, "q50": 0.0, "q90": 1.28}, index=y.index)  # assumes sd = 1
        cal = aci.apply(q)
        cover.append(((y >= cal["q10"]) & (y <= cal["q90"])).mean())
        aci.update(cal, y)
    assert abs(np.mean(cover[-100:]) - 0.8) < 0.05
    assert 1.6 < aci.scale < 2.5


def test_psi_detects_shift():
    rng = np.random.default_rng(0)
    ref = rng.normal(0, 1, 5000)
    assert psi(ref, rng.normal(0, 1, 500)) < 0.1
    assert psi(ref, rng.normal(1.5, 1, 500)) > 0.25


def test_investment_math():
    r = evaluate(InvestmentInput(power_mw=1, duration_h=2, capex_eur_per_kwh=100, fixed_opex_pct=0,
                                 revenue_eur_per_mw_year=50_000, revenue_decline_pct=0,
                                 lifetime_years=10, discount_rate=0.0))
    assert r["capex_eur"] == 200_000 and r["npv_eur"] == 300_000 and r["payback_years"] == 4.0
