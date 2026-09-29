"""Gradient-boosted quantile regression (LightGBM), one booster per quantile.

* recency weighting (half-life 180 d): price regimes drift with gas/CO2
* native TreeSHAP (`pred_contrib=True`) for per-hour explanations —
  no extra dependency, microseconds per row.
"""
from __future__ import annotations

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from ..config import get_settings
from ..features.builder import FEATURES, training_rows
from .base import QCOLS, Forecaster

PARAMS = {
    "objective": "quantile",
    "learning_rate": 0.1,
    "max_bin": 63,
    "num_leaves": 31,
    "min_data_in_leaf": 40,
    "feature_fraction": 0.85,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "verbose": -1,
}
N_ROUNDS = 220
HALF_LIFE_DAYS = 180


class LGBMQuantile(Forecaster):
    name = "lgbm"
    family = "gradient_boosting"

    def __init__(self, quantiles=(0.1, 0.5, 0.9), n_rounds: int = N_ROUNDS) -> None:
        self.quantiles = quantiles
        self.n_rounds = n_rounds
        self.boosters: dict[float, lgb.Booster] = {}
        self.features = list(FEATURES)

    def fit(self, feat: pd.DataFrame, before: pd.Timestamp) -> LGBMQuantile:
        rows = training_rows(feat, before)
        X = rows[self.features].astype("float32")
        y = rows["price"].to_numpy()
        age = (pd.Timestamp(before) - rows["delivery_date"]).dt.days.to_numpy()
        w = 0.5 ** (age / HALF_LIFE_DAYS) + 0.15
        seed = get_settings().seed
        for q in self.quantiles:
            ds = lgb.Dataset(X, y, weight=w, free_raw_data=False)
            params = {**PARAMS, "alpha": q, "seed": seed, "num_threads": 0}
            self.boosters[q] = lgb.train(params, ds, num_boost_round=self.n_rounds)
        return self

    def predict(self, feat: pd.DataFrame, days: list[pd.Timestamp]) -> pd.DataFrame:
        rows = feat[feat["delivery_date"].isin(days)]
        X = rows[self.features].astype("float32")
        out = pd.DataFrame(
            {c: self.boosters[q].predict(X) for c, q in zip(QCOLS, self.quantiles)},
            index=rows.index,
        )
        return self.monotone(out)

    # ---- explainability -----------------------------------------------------
    def shap(self, rows: pd.DataFrame) -> pd.DataFrame:
        """TreeSHAP contributions of the median model (EUR/MWh per feature)."""
        X = rows[self.features].astype("float32")
        contrib = self.boosters[0.5].predict(X, pred_contrib=True)
        cols = self.features + ["_base"]
        return pd.DataFrame(contrib, index=rows.index, columns=cols)

    def importance(self) -> pd.Series:
        b = self.boosters[0.5]
        imp = pd.Series(b.feature_importance("gain"), index=self.features)
        return (imp / imp.sum()).sort_values(ascending=False)

    # ---- persistence ------------------------------------------------------
    def save(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        for q, b in self.boosters.items():
            b.save_model(str(path / f"lgbm_q{int(q * 100):02d}.txt"))
        (path / "lgbm_meta.json").write_text(
            json.dumps({"quantiles": list(self.quantiles), "features": self.features})
        )

    @classmethod
    def load(cls, path: Path) -> LGBMQuantile:
        meta = json.loads((path / "lgbm_meta.json").read_text())
        m = cls(tuple(meta["quantiles"]))
        m.features = meta["features"]
        for q in m.quantiles:
            m.boosters[q] = lgb.Booster(model_file=str(path / f"lgbm_q{int(q * 100):02d}.txt"))
        return m


def global_shap_importance(model: LGBMQuantile, rows: pd.DataFrame) -> pd.Series:
    sv = model.shap(rows).drop(columns="_base")
    imp = sv.abs().mean().sort_values(ascending=False)
    return imp / imp.sum() * 100 if imp.sum() > 0 else imp


def top_drivers(model: LGBMQuantile, rows: pd.DataFrame, k: int = 5) -> list[dict]:
    """Day-level drivers: mean SHAP over the day, signed, in EUR/MWh."""
    sv = model.shap(rows).drop(columns="_base").mean()
    top = sv.reindex(sv.abs().sort_values(ascending=False).index[:k])
    vals = rows[model.features].mean()
    return [
        {"feature": f, "impact_eur_mwh": round(float(v), 2), "value": round(float(vals[f]), 3)
         if np.isfinite(vals[f]) else None}
        for f, v in top.items()
    ]
