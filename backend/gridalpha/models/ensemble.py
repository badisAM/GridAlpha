"""Online expert aggregation + adaptive conformal calibration.

* OnlineEnsemble: weights each expert by a softmax of its recent relative
  pinball loss (last N settled days). Leakage-free: when forecasting day D
  (at D-1 11:00) the prices of D-1 are already public, so every loss used
  is observable at decision time.
* AdaptiveConformal: ACI-style online recalibration (Gibbs & Candes,
  NeurIPS 2021). The 80 % band is scaled by s_t, updated after each
  settled day:  log s <- log s + gamma * (miss_rate - (1 - target)).
  Keeps empirical coverage on target under regime shifts without
  retraining anything.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import QCOLS


def softmax_weights(recent_loss: pd.DataFrame, temperature: float) -> dict[str, float]:
    """recent_loss: rows = days, columns = experts (mean daily pinball)."""
    names = list(recent_loss.columns)
    if recent_loss.dropna(how="all").empty:
        return {n: 1.0 / len(names) for n in names}
    L = recent_loss.mean(skipna=True)
    L = L.fillna(L.max())
    rel = L / max(float(L.min()), 1e-9) - 1.0
    w = np.exp(-rel / max(temperature, 1e-6))
    w = w / w.sum()
    return {n: float(w[n]) for n in names}


def combine(preds: dict[str, pd.DataFrame], weights: dict[str, float]) -> pd.DataFrame:
    """Quantile averaging (Vincentisation) of expert forecasts."""
    idx = None
    for p in preds.values():
        idx = p.index if idx is None else idx.intersection(p.index)
    out = sum(weights[n] * preds[n].loc[idx, QCOLS] for n in preds)
    return out


class AdaptiveConformal:
    def __init__(self, target: float = 0.8, gamma: float = 0.05, log_scale: float = 0.0) -> None:
        self.target = target
        self.gamma = gamma
        self.log_scale = log_scale

    @property
    def scale(self) -> float:
        return float(np.exp(self.log_scale))

    def apply(self, q: pd.DataFrame) -> pd.DataFrame:
        s = self.scale
        out = q.copy()
        out["q10"] = q["q50"] - s * (q["q50"] - q["q10"])
        out["q90"] = q["q50"] + s * (q["q90"] - q["q50"])
        return out

    def update(self, q: pd.DataFrame, actual: pd.Series) -> float:
        a = actual.reindex(q.index)
        ok = a.notna()
        if not ok.any():
            return self.scale
        miss = float(((a[ok] < q.loc[ok, "q10"]) | (a[ok] > q.loc[ok, "q90"])).mean())
        self.log_scale += self.gamma * (miss - (1 - self.target)) * 10
        self.log_scale = float(np.clip(self.log_scale, np.log(0.3), np.log(4.0)))
        return self.scale
