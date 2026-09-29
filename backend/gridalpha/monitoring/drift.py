"""Model monitoring: data drift (PSI) + performance drift (rolling errors).

PSI (Population Stability Index) compares the recent distribution of each
key feature with its training reference:
    < 0.10 stable | 0.10-0.25 moderate shift | > 0.25 significant shift
Performance drift uses the walk-forward forecasts: rolling MAE and
interval coverage vs their backtest averages.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

KEY_FEATURES = ["res_proxy", "solar_proxy", "wind_proxy", "load_proxy", "temp_fc",
                "wind100_n_fc", "rad_s_fc", "p_d1_mean", "p_d1_std", "ttf_lag"]
# slowly-moving *level* variables (random-walk like): PSI on a 4-week window is
# meaningless, what matters for tree models is extrapolation outside the
# training range -> "out-of-distribution share"
LEVEL_FEATURES = {"p_d1_mean", "p_d1_std", "ttf_lag"}


def psi(ref: np.ndarray, cur: np.ndarray, bins: int = 10, min_ref: int = 50,
        min_cur: int = 24) -> float:
    ref, cur = ref[np.isfinite(ref)], cur[np.isfinite(cur)]
    if len(ref) < min_ref or len(cur) < min_cur:
        return float("nan")
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    r = np.histogram(ref, edges)[0] / len(ref)
    c = np.histogram(cur, edges)[0] / len(cur)
    r, c = np.clip(r, 1e-3, None), np.clip(c, 1e-3, None)
    return float(np.sum((c - r) * np.log(c / r)))


def _status(v: float) -> str:
    if not np.isfinite(v):
        return "n/a"
    return "stable" if v < 0.1 else "moderate" if v < 0.25 else "significant"


def data_drift(feat: pd.DataFrame, cur_days: int = 28, half_window: int = 21) -> list[dict]:
    """PSI of the last `cur_days` vs a *seasonally matched* reference: the same
    calendar window (+/- `half_window` days) in previous years. Comparing
    September with a full year would flag normal seasonality as drift."""
    known = feat[feat["price"].notna()]
    last = known["delivery_date"].max()
    cur = feat[(feat["delivery_date"] > last - pd.Timedelta(days=cur_days))
               & (feat["delivery_date"] <= last + pd.Timedelta(days=1))]
    mid = last - pd.Timedelta(days=cur_days // 2)
    masks = []
    for k in range(1, 6):
        c = mid - pd.DateOffset(years=k)
        masks.append((known["delivery_date"] >= c - pd.Timedelta(days=half_window))
                     & (known["delivery_date"] <= c + pd.Timedelta(days=half_window)))
    ref = known[np.logical_or.reduce(masks)]
    out = []
    for f in KEY_FEATURES:
        if f not in feat:
            continue
        rec = {
            "feature": f,
            "ref_mean": round(float(ref[f].mean()), 2) if ref[f].notna().any() else None,
            "cur_mean": round(float(cur[f].mean()), 2) if cur[f].notna().any() else None,
        }
        if f in LEVEL_FEATURES:
            hist = known[f].to_numpy(dtype=float)
            hist = hist[np.isfinite(hist)]
            curv = cur[f].to_numpy(dtype=float)
            curv = curv[np.isfinite(curv)]
            if len(hist) and len(curv):
                lo, hi = np.quantile(hist, [0.005, 0.995])
                ood = float(np.mean((curv < lo) | (curv > hi)))
            else:
                ood = float("nan")
            rec.update(metric="ood_share", value=None if not np.isfinite(ood) else round(ood, 4),
                       status="n/a" if not np.isfinite(ood) else
                       "stable" if ood < 0.05 else "moderate" if ood < 0.2 else "significant")
        else:
            v = psi(ref[f].to_numpy(dtype=float), cur[f].to_numpy(dtype=float))
            rec.update(metric="psi", value=None if not np.isfinite(v) else round(v, 4), status=_status(v))
        out.append(rec)
    return sorted(out, key=lambda r: -(r["value"] or 0))


def performance_drift(forecasts: pd.DataFrame, model: str = "ensemble", window: int = 7) -> dict:
    f = forecasts[forecasts["model"] == model].copy()
    if f.empty:
        return {}
    f["abs_err"] = (f["actual"] - f["q50"]).abs()
    f["inside"] = ((f["actual"] >= f["q10"]) & (f["actual"] <= f["q90"])).astype(float)
    daily = f.groupby("delivery_date").agg(mae=("abs_err", "mean"), coverage=("inside", "mean"))
    roll = daily.rolling(window, min_periods=3).mean()
    overall_mae = float(daily["mae"].mean())
    recent_mae = float(roll["mae"].iloc[-1])
    recent_cov = float(roll["coverage"].iloc[-1])
    ratio = recent_mae / overall_mae if overall_mae else float("nan")
    status = "healthy" if ratio < 1.25 and 0.65 <= recent_cov <= 0.92 else \
        "watch" if ratio < 1.6 else "degraded"
    series = roll.reset_index().dropna()
    return {
        "model": model,
        "window_days": window,
        "overall_mae": round(overall_mae, 2),
        "recent_mae": round(recent_mae, 2),
        "mae_ratio": round(ratio, 3),
        "recent_coverage": round(recent_cov, 3),
        "status": status,
        "retrain_recommended": status == "degraded",
        "series": [
            {"date": str(r.delivery_date.date()), "mae": round(r.mae, 2), "coverage": round(r.coverage, 3)}
            for r in series.itertuples()
        ],
    }
