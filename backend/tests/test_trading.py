from __future__ import annotations

import numpy as np
import pytest

from gridalpha.trading.battery import BatterySpec, optimise, settle
from gridalpha.trading.scenarios import quantile_scenarios

SPEC = BatterySpec(power_mw=10, energy_mwh=20, rte=0.88, max_cycles_per_day=1.5,
                   degradation_eur_per_mwh=8.0)


def _check_physics(res, spec=SPEC):
    E = spec.energy_mwh
    assert (res.charge >= -1e-6).all() and (res.discharge >= -1e-6).all()
    assert (res.charge <= spec.power_mw + 1e-6).all() and (res.discharge <= spec.power_mw + 1e-6).all()
    assert (res.soc >= spec.soc_min_frac * E - 1e-6).all() and (res.soc <= spec.soc_max_frac * E + 1e-6).all()
    assert (np.minimum(res.charge, res.discharge) < 1e-6).all()           # never both
    assert res.discharge.sum() <= spec.max_cycles_per_day * E + 1e-6       # warranty
    assert res.soc[-1] >= spec.soc_init_frac * E - 1e-6                    # energy neutral
    # state-of-charge dynamics hold exactly
    s_prev = spec.soc_init_frac * E
    for c, d, s in zip(res.charge, res.discharge, res.soc):
        assert abs(s - (s_prev + spec.eta * c - d / spec.eta)) < 1e-5
        s_prev = s


def test_flat_prices_stay_idle():
    res = optimise(SPEC, np.full(24, 80.0))
    _check_physics(res)
    assert res.discharge.sum() < 1e-6 and res.expected_pnl == pytest.approx(0, abs=1e-6)


def test_obvious_arbitrage():
    p = np.array([100] * 6 + [10] * 4 + [60] * 8 + [200] * 3 + [90] * 3, dtype=float)
    res = optimise(SPEC, p)
    _check_physics(res)
    assert res.charge[6:10].sum() > 15          # buys the cheap block
    assert res.discharge[18:21].sum() > 15      # sells the evening peak
    assert res.expected_pnl > 0
    assert res.solve_ms < 2000


def test_negative_prices_are_monetised():
    p = np.array([50] * 10 + [-40] * 4 + [50] * 5 + [150] * 5, dtype=float)
    res = optimise(SPEC, p)
    _check_physics(res)
    assert res.charge[10:14].sum() > 10


def test_settle_matches_objective():
    rng = np.random.default_rng(0)
    p = 80 + 40 * np.sin(np.arange(24) / 3) + rng.normal(0, 5, 24)
    res = optimise(SPEC, p)
    assert settle(p, res.charge, res.discharge, SPEC) == pytest.approx(res.expected_pnl, rel=1e-6)


def test_scenarios_reproduce_quantiles():
    q50 = np.linspace(40, 120, 24)
    q10, q90 = q50 - 20, q50 + 35
    sc = quantile_scenarios(q10, q50, q90, n=20000, rho=0.8, seed=3)
    assert np.allclose(np.quantile(sc, 0.1, axis=0), q10, atol=1.5)
    assert np.allclose(np.quantile(sc, 0.5, axis=0), q50, atol=1.5)
    assert np.allclose(np.quantile(sc, 0.9, axis=0), q90, atol=1.5)


def test_cvar_improves_tail():
    rng = np.random.default_rng(1)
    q50 = 80 + 50 * np.sin((np.arange(24) - 8) / 24 * 2 * np.pi)
    sc = quantile_scenarios(q50 - 40, q50, q50 + 40, n=200, seed=2) + rng.normal(0, 5, (200, 24))
    neutral = optimise(SPEC, q50, sc, risk_aversion=0.0)
    averse = optimise(SPEC, q50, sc, risk_aversion=0.8)
    _check_physics(averse)
    assert averse.risk()["cvar"] >= neutral.risk()["cvar"] - 1e-6
    assert neutral.expected_pnl >= averse.expected_pnl - 1e-6
