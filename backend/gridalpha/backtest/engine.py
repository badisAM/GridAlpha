"""Walk-forward backtest: forecast -> optimise -> settle, one day at a time.

Protocol (mirrors a real trading desk, no look-ahead):
1. models are re-trained every `retrain_every_days` on days < first day of
   the block (expanding window);
2. for each delivery day D, ensemble weights and conformal scale use only
   days < D (D-1 prices are public before D's gate closure);
3. each strategy commits a 24-hour schedule, settled at realised prices;
4. perfect foresight (oracle) gives the revenue ceiling -> capture ratio.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import get_settings
from ..log import get_logger
from ..models.baselines import NaiveD1, NaiveD7, Profile7
from ..models.ensemble import AdaptiveConformal, combine, softmax_weights
from ..models.lgbm import LGBMQuantile
from ..models.metrics import daily_pinball, forecast_metrics
from ..trading.battery import BatterySpec, optimise, settle
from ..trading.scenarios import estimate_rho, quantile_scenarios

log = get_logger("backtest")

ENSEMBLE_MEMBERS = ("lgbm", "tide")
DET_STRATEGIES = ("naive_d1", "profile7", "lgbm", "tide", "ensemble")


@dataclass
class BacktestResult:
    forecasts: pd.DataFrame
    dispatch: pd.DataFrame
    daily: pd.DataFrame
    weights: pd.DataFrame
    summary: dict = field(default_factory=dict)
    models: list = field(default_factory=list)  # last-block experts (for warm starts)


def complete_days(feat: pd.DataFrame) -> pd.DatetimeIndex:
    g = feat.groupby("delivery_date")["price"]
    ok = (g.count() >= 23) & (g.count() == g.size())
    return pd.DatetimeIndex(ok[ok].index)


def build_models():
    s = get_settings()
    models = [NaiveD1(), NaiveD7(), Profile7(), LGBMQuantile(s.quantiles)]
    if s.enable_deep_model:
        try:
            from ..models.tide import TORCH_OK, TiDEQuantile

            if TORCH_OK:
                models.append(TiDEQuantile())
            else:
                log.warning("torch not installed — deep model disabled")
        except Exception as exc:  # pragma: no cover
            log.warning("deep model unavailable: %s", exc)
    return models


def trading_metrics(daily: pd.DataFrame, spec: BatterySpec) -> dict:
    out = {}
    oracle = daily[daily.strategy == "oracle"].set_index("delivery_date")["pnl"]
    for strat, g in daily.groupby("strategy"):
        pnl = g.set_index("delivery_date")["pnl"]
        cum = pnl.cumsum()
        dd = float((cum - cum.cummax()).min())
        n = len(pnl)
        k5 = max(1, int(np.ceil(0.05 * n)))
        out[strat] = {
            "days": n,
            "total_pnl_eur": round(float(pnl.sum()), 0),
            "eur_per_mw_year": round(float(pnl.sum()) / n * 365 / spec.power_mw, 0),
            "capture_ratio": round(float(pnl.sum() / oracle.reindex(pnl.index).sum()), 4),
            "daily_pnl_std_eur": round(float(pnl.std()), 0),
            "cvar5_day_eur": round(float(np.sort(pnl.to_numpy())[:k5].mean()), 0),
            "max_drawdown_eur": round(dd, 0),
            "worst_day_eur": round(float(pnl.min()), 0),
            "loss_day_share": round(float((pnl < 0).mean()), 4),
            "avg_cycles_per_day": round(float(g["cycles"].mean()), 3),
            "forecast_bias_eur": round(float((g["expected_pnl"] - g["pnl"]).mean()), 1),
        }
    return out


def run_backtest(feat: pd.DataFrame, days: int | None = None, retrain_every: int | None = None,
                 spec: BatterySpec | None = None) -> BacktestResult:
    s = get_settings()
    days = days or s.backtest_days
    retrain_every = retrain_every or s.retrain_every_days
    spec = spec or BatterySpec(
        power_mw=s.battery_power_mw, energy_mwh=s.battery_energy_mwh, rte=s.battery_rte,
        max_cycles_per_day=s.battery_max_cycles_per_day, soc_init_frac=s.battery_soc_init,
        degradation_eur_per_mwh=s.degradation_eur_per_mwh,
    )
    timings: dict[str, float] = {"fit_s": 0.0, "predict_s": 0.0, "optimise_s": 0.0}

    test_days = complete_days(feat)[-days:]
    models = build_models()
    log.info("backtest: %d days (%s -> %s), models=%s, retrain every %d d",
             len(test_days), test_days[0].date(), test_days[-1].date(),
             [m.name for m in models], retrain_every)

    # ---- 1. walk-forward forecasts per expert --------------------------------
    preds: dict[str, list[pd.DataFrame]] = {m.name: [] for m in models}
    fit_log = []
    for i in range(0, len(test_days), retrain_every):
        block = list(test_days[i:i + retrain_every])
        for m in models:
            t0 = time.perf_counter()
            m.fit(feat, block[0])
            t1 = time.perf_counter()
            preds[m.name].append(m.predict(feat, block))
            t2 = time.perf_counter()
            timings["fit_s"] += t1 - t0
            timings["predict_s"] += t2 - t1
        fit_log.append({"cutoff": str(block[0].date()), "n_days": len(block)})
        log.info("  block %s (+%d d) done", block[0].date(), len(block))
    P = {n: pd.concat(v).sort_index() for n, v in preds.items()}

    meta = feat[["delivery_date", "hour", "price"]].rename(columns={"price": "actual"})

    def with_meta(df: pd.DataFrame) -> pd.DataFrame:
        return df.join(meta, how="left")

    # ---- 2. online ensemble + adaptive conformal ------------------------------
    members = [n for n in ENSEMBLE_MEMBERS if n in P]
    losses = pd.DataFrame({n: daily_pinball(with_meta(P[n])) for n in members})
    aci = AdaptiveConformal(s.conformal_target_coverage, s.conformal_gamma)
    ens_parts, w_rows = [], []
    for d in test_days:
        recent = losses[losses.index < d].tail(s.ensemble_window_days)
        w = softmax_weights(recent, s.ensemble_temperature)
        day_preds = {n: P[n][meta.loc[P[n].index, "delivery_date"] == d] for n in members}
        raw = combine(day_preds, w)
        cal = aci.apply(raw)
        ens_parts.append(cal)
        w_rows.append({"delivery_date": d, **{f"w_{n}": v for n, v in w.items()},
                       "conformal_scale": aci.scale})
        aci.update(cal, meta.loc[raw.index, "actual"])
    P["ensemble"] = pd.concat(ens_parts).sort_index()
    weights = pd.DataFrame(w_rows)

    forecasts = []
    for n, p in P.items():
        f = with_meta(p)
        f["model"] = n
        forecasts.append(f)
    forecasts = pd.concat(forecasts)
    forecasts.index.name = "ts"
    forecasts = forecasts.reset_index()

    # ---- 3. decisions & settlement ---------------------------------------------
    ens = with_meta(P["ensemble"])
    std_res = []
    disp_rows, daily_rows = [], []
    t_opt = time.perf_counter()
    for d in test_days:
        act_day = meta[meta["delivery_date"] == d]
        idx = act_day.index
        actual = act_day["actual"].to_numpy()
        plans: dict[str, tuple] = {"oracle": (optimise(spec, actual), actual)}
        for strat in DET_STRATEGIES:
            if strat not in P:
                continue
            q = P[strat].reindex(idx)
            if q["q50"].isna().any():
                continue
            plans[strat] = (optimise(spec, q["q50"].to_numpy()), q["q50"].to_numpy())
        # risk-aware stochastic strategy on calibrated ensemble quantiles
        q = ens.reindex(idx)
        rho = estimate_rho(std_res[-60:]) if len(std_res) >= 14 else 0.85
        scen = quantile_scenarios(q["q10"].to_numpy(), q["q50"].to_numpy(), q["q90"].to_numpy(),
                                  n=s.n_scenarios, rho=rho, seed=int(d.strftime("%Y%m%d")))
        plans["ensemble_cvar"] = (
            optimise(spec, q["q50"].to_numpy(), scen, s.risk_aversion, s.cvar_alpha),
            q["q50"].to_numpy(),
        )
        # standardised residuals for the copula (known after settlement)
        width = np.maximum((q["q90"] - q["q10"]).to_numpy(), 1e-3) / (2 * 1.2816)
        std_res.append((actual - q["q50"].to_numpy()) / width)

        for strat, (res, _) in plans.items():
            pnl = settle(actual, res.charge, res.discharge, spec)
            daily_rows.append({
                "delivery_date": d, "strategy": strat, "pnl": pnl,
                "expected_pnl": res.expected_pnl,
                "cycles": float(res.discharge.sum() / spec.energy_mwh),
                "solve_ms": res.solve_ms,
            })
            disp_rows.append(pd.DataFrame({
                "ts": idx, "delivery_date": d, "strategy": strat,
                "charge": res.charge, "discharge": res.discharge, "soc": res.soc,
                "price": actual,
            }))
    timings["optimise_s"] = time.perf_counter() - t_opt
    daily = pd.DataFrame(daily_rows)
    dispatch = pd.concat(disp_rows, ignore_index=True)

    # ---- 4. summary ---------------------------------------------------------------
    fmetrics = {n: forecast_metrics(g) for n, g in forecasts.groupby("model")}
    tmetrics = trading_metrics(daily, spec)
    last_losses = losses.tail(s.ensemble_window_days)
    summary = {
        "period": {"start": str(test_days[0].date()), "end": str(test_days[-1].date()),
                   "days": len(test_days)},
        "battery": spec.as_dict(),
        "config": {"retrain_every_days": retrain_every, "risk_aversion": s.risk_aversion,
                   "cvar_alpha": s.cvar_alpha, "n_scenarios": s.n_scenarios,
                   "ensemble_members": members},
        "forecast_metrics": fmetrics,
        "trading_metrics": tmetrics,
        "latest_weights": softmax_weights(last_losses, s.ensemble_temperature),
        "latest_conformal_log_scale": aci.log_scale,
        "copula_rho": estimate_rho(std_res[-60:]),
        "retrains": fit_log,
        "timings_s": {k: round(v, 2) for k, v in timings.items()},
        "avg_solve_ms": round(float(daily["solve_ms"].mean()), 2),
    }
    log.info("backtest done: %s", {k: v["capture_ratio"] for k, v in tmetrics.items()})
    return BacktestResult(forecasts, dispatch, daily, weights, summary, models)
