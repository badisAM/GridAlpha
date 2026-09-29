"""Common interface for every price forecaster (baselines, GBM, deep)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np
import pandas as pd

from ..features.builder import training_rows

QCOLS = ["q10", "q50", "q90"]


class Forecaster(ABC):
    name: str = "base"
    family: str = "baseline"

    @abstractmethod
    def fit(self, feat: pd.DataFrame, before: pd.Timestamp) -> Forecaster:
        """Train on delivery days strictly before `before`."""

    @abstractmethod
    def predict(self, feat: pd.DataFrame, days: list[pd.Timestamp]) -> pd.DataFrame:
        """Hourly quantiles for `days`: index = ts (UTC), columns = QCOLS."""

    def save(self, path: Path) -> None:  # pragma: no cover - optional
        path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def monotone(df: pd.DataFrame) -> pd.DataFrame:
        arr = np.sort(df[QCOLS].to_numpy(), axis=1)
        return pd.DataFrame(arr, index=df.index, columns=QCOLS)


class ResidualIntervalMixin:
    """Turns a point forecast into quantiles using empirical residual
    quantiles by hour, estimated on the last `window` training days."""

    window_days = 90
    _res_q: pd.DataFrame | None = None

    def _fit_residuals(self, feat: pd.DataFrame, before: pd.Timestamp, point_col: str) -> None:
        rows = training_rows(feat, before)
        rows = rows[rows["delivery_date"] >= pd.Timestamp(before) - pd.Timedelta(days=self.window_days)]
        rows = rows[rows[point_col].notna()]
        res = rows["price"] - rows[point_col]
        self._res_q = res.groupby(rows["hour"]).quantile([0.1, 0.5, 0.9]).unstack()

    def _interval(self, rows: pd.DataFrame, point: pd.Series) -> pd.DataFrame:
        rq = self._res_q.reindex(rows["hour"].to_numpy())
        out = pd.DataFrame(index=rows.index)
        out["q10"] = point.to_numpy() + rq[0.1].to_numpy()
        out["q50"] = point.to_numpy()
        out["q90"] = point.to_numpy() + rq[0.9].to_numpy()
        return Forecaster.monotone(out)
