"""The most important test of the repo: no look-ahead leakage."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from gridalpha.data.sources.synthetic import simulate_market
from gridalpha.features.builder import FEATURES, build_features
from gridalpha.timeutils import TZ


@pytest.fixture(scope="module")
def frame():
    return simulate_market(date(2025, 1, 1), date(2025, 6, 30), date(2025, 6, 28), seed=1)


def test_no_lookahead_leakage(frame):
    """Features of delivery day D must not change when we tamper with
    anything unknown at gate closure (D-1 12:00): prices of D and later,
    actual generation/load after D-1 10:00."""
    base = build_features(frame)
    D = pd.Timestamp("2025-05-20")
    local = frame.index.tz_convert(TZ)
    t = frame.copy()
    after_d = local.tz_localize(None) >= D
    t.loc[after_d, "price"] = t.loc[after_d, "price"] * 3 + 500
    cutoff = (D - pd.Timedelta(days=1)) + pd.Timedelta(hours=10)
    after_cut = local.tz_localize(None) >= cutoff
    for c in ("load", "solar", "wind_onshore", "wind_offshore"):
        t.loc[after_cut, c] = t.loc[after_cut, c] * 5
    tampered = build_features(t)
    a = base[base["delivery_date"] == D][FEATURES]
    b = tampered[tampered["delivery_date"] == D][FEATURES]
    pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-9)


def test_feature_frame_is_complete(frame):
    f = build_features(frame)
    rows = f[f["delivery_date"] >= pd.Timestamp("2025-03-01")]
    rows = rows[rows["price"].notna()]
    assert rows[FEATURES].isna().mean().max() < 0.01
    assert rows["res_proxy"].corr(rows["price"]) > 0.6  # merit-order signal is there


def test_dst_days_have_correct_length(frame):
    f = build_features(frame)
    sizes = f.groupby("delivery_date").size()
    assert sizes[pd.Timestamp("2025-03-30")] == 23  # spring forward
    assert sizes[pd.Timestamp("2025-03-31")] == 24


def test_simulator_is_calibrated():
    df = simulate_market(date(2025, 1, 1), date(2025, 12, 31), date(2025, 12, 31), seed=42)
    p = df["price"]
    assert 70 < p.mean() < 110          # 2025 real: ~89 EUR/MWh
    assert 300 < (p < 0).sum() < 1100   # 2025 real: ~575 h
    assert np.isfinite(p).all()
