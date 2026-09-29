"""Forecast metrics — statistical *and* decision-relevant.

For a battery, what pays is ranking the hours correctly (buy the cheapest,
sell the dearest), so next to MAE/RMSE we report Kendall's tau per day and
the peak/trough-hour hit rates. Recent literature (e.g. arXiv:2604.12082)
shows rank correlation, not MAE, predicts arbitrage value.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import kendalltau


def pinball(y: np.ndarray, q: np.ndarray, tau: float) -> float:
    d = y - q
    return float(np.nanmean(np.maximum(tau * d, (tau - 1) * d)))


def forecast_metrics(df: pd.DataFrame, quantiles=(0.1, 0.5, 0.9)) -> dict:
    """`df` needs columns: delivery_date, actual, q10, q50, q90."""
    y = df["actual"].to_numpy()
    m = df["q50"].to_numpy()
    err = y - m
    out = {
        "n_hours": int(np.isfinite(err).sum()),
        "mae": float(np.nanmean(np.abs(err))),
        "rmse": float(np.sqrt(np.nanmean(err**2))),
        "bias": float(np.nanmean(-err)),
    }
    cols = {0.1: "q10", 0.5: "q50", 0.9: "q90"}
    out["pinball"] = float(np.mean([pinball(y, df[cols[t]].to_numpy(), t) for t in quantiles]))
    inside = (y >= df["q10"].to_numpy()) & (y <= df["q90"].to_numpy())
    out["coverage_80"] = float(np.nanmean(inside))
    out["interval_width"] = float(np.nanmean(df["q90"] - df["q10"]))

    taus, peak_hit, trough_hit = [], [], []
    for _, g in df.groupby("delivery_date"):
        if len(g) < 20 or g["actual"].isna().any():
            continue
        t = kendalltau(g["actual"], g["q50"]).statistic
        if np.isfinite(t):
            taus.append(t)
        a, f = g["actual"].to_numpy(), g["q50"].to_numpy()
        peak_hit.append(abs(int(np.argmax(a)) - int(np.argmax(f))) <= 1)
        trough_hit.append(abs(int(np.argmin(a)) - int(np.argmin(f))) <= 1)
    out["kendall_tau"] = float(np.mean(taus)) if taus else float("nan")
    out["peak_hour_hit"] = float(np.mean(peak_hit)) if peak_hit else float("nan")
    out["trough_hour_hit"] = float(np.mean(trough_hit)) if trough_hit else float("nan")

    neg = y < 0
    out["neg_price_recall"] = (
        float(np.mean(m[neg] < 5)) if neg.any() else float("nan")
    )  # did we flag (near-)negative hours?
    spikes = y > np.nanpercentile(y, 95)
    out["spike_mae"] = float(np.nanmean(np.abs(err[spikes]))) if spikes.any() else float("nan")
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in out.items()}


def daily_pinball(df: pd.DataFrame) -> pd.Series:
    """Mean pinball loss per delivery day (used for online ensemble weights)."""
    def _one(g: pd.DataFrame) -> float:
        y = g["actual"].to_numpy()
        return np.mean([
            pinball(y, g["q10"].to_numpy(), 0.1),
            pinball(y, g["q50"].to_numpy(), 0.5),
            pinball(y, g["q90"].to_numpy(), 0.9),
        ])
    return df.groupby("delivery_date").apply(_one)
