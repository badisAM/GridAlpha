"""BESS investment case: NPV / IRR / payback from backtested revenues.

Revenue input comes from the walk-forward backtest (EUR/MW/year of the
chosen strategy), so the business case is tied to measured model quality —
+1 pt of capture ratio is directly visible in NPV.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class InvestmentInput:
    power_mw: float = 10.0
    duration_h: float = 2.0
    capex_eur_per_kwh: float = 250.0
    fixed_opex_pct: float = 0.02          # of capex per year
    revenue_eur_per_mw_year: float = 60_000.0
    revenue_decline_pct: float = 0.02     # capacity fade + market cannibalisation
    lifetime_years: int = 15
    discount_rate: float = 0.08


def _npv(rate: float, flows: np.ndarray) -> float:
    t = np.arange(len(flows))
    return float(np.sum(flows / (1 + rate) ** t))


def _irr(flows: np.ndarray) -> float | None:
    lo, hi = -0.99, 1.5
    f_lo, f_hi = _npv(lo, flows), _npv(hi, flows)
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = _npv(mid, flows)
        if abs(f_mid) < 1e-6:
            break
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return float(mid)


def evaluate(inp: InvestmentInput) -> dict:
    capex = inp.capex_eur_per_kwh * inp.power_mw * inp.duration_h * 1000
    years = np.arange(1, inp.lifetime_years + 1)
    revenue = inp.revenue_eur_per_mw_year * inp.power_mw * (1 - inp.revenue_decline_pct) ** (years - 1)
    opex = inp.fixed_opex_pct * capex * np.ones_like(revenue)
    cash = revenue - opex
    flows = np.concatenate([[-capex], cash])
    cum = np.cumsum(flows)
    payback = None
    for y in range(1, len(cum)):
        if cum[y] >= 0:
            prev = cum[y - 1]
            payback = round(y - 1 + (-prev) / (cum[y] - prev), 2)
            break
    return {
        "capex_eur": round(capex, 0),
        "npv_eur": round(_npv(inp.discount_rate, flows), 0),
        "irr": None if (irr := _irr(flows)) is None else round(irr, 4),
        "payback_years": payback,
        "year1_revenue_eur": round(float(revenue[0]), 0),
        "cashflows": [{"year": int(y), "revenue": round(float(r), 0), "opex": round(float(o), 0),
                       "cumulative": round(float(c), 0)}
                      for y, r, o, c in zip(years, revenue, opex, cum[1:])],
    }
