"""Honest baselines. Any ML model must beat these to justify its cost.

* naive_d1  — tomorrow = today, hour by hour (what many desks still do)
* naive_d7  — same hour last week (captures weekly seasonality)
* profile7  — 7-day average hourly shape ("climatological bidder")
"""
from __future__ import annotations

import pandas as pd

from .base import Forecaster, ResidualIntervalMixin


class _ColumnBaseline(ResidualIntervalMixin, Forecaster):
    column = "p_lag1d"

    def fit(self, feat: pd.DataFrame, before: pd.Timestamp) -> _ColumnBaseline:
        self._fit_residuals(feat, before, self.column)
        return self

    def predict(self, feat: pd.DataFrame, days: list[pd.Timestamp]) -> pd.DataFrame:
        rows = feat[feat["delivery_date"].isin(days)]
        point = rows[self.column].fillna(rows["p_d1_mean"])
        return self._interval(rows, point)


class NaiveD1(_ColumnBaseline):
    name, column = "naive_d1", "p_lag1d"


class NaiveD7(_ColumnBaseline):
    name, column = "naive_d7", "p_lag7d"


class Profile7(_ColumnBaseline):
    name, column = "profile7", "p_hour_mean7"


BASELINES = [NaiveD1, NaiveD7, Profile7]
