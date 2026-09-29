"""Data-quality gate (DataOps). Runs after every ingestion; results are
stored with the data and shown in the Monitoring page."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..timeutils import now_local

# physically plausible ranges for DE-LU (harmonised SDAC price limits)
RANGES = {
    "price": (-500.0, 4000.0),
    "load": (20_000.0, 95_000.0),
    "solar": (0.0, 90_000.0),
    "wind_onshore": (0.0, 70_000.0),
    "wind_offshore": (0.0, 12_000.0),
    "temp_fc": (-35.0, 45.0),
    "wind100_n_fc": (0.0, 45.0),
    "rad_s_fc": (0.0, 1200.0),
    "cloud_fc": (0.0, 100.0),
    "ttf": (3.0, 400.0),
}


def run_quality_checks(frame: pd.DataFrame) -> dict:
    now = now_local().tz_convert("UTC")
    hist = frame[frame.index <= now]
    checks = []
    worst = "pass"
    for col, (lo, hi) in RANGES.items():
        if col not in frame:
            continue
        s = hist[col]
        valid = s.dropna()
        coverage = float(len(valid) / max(len(s), 1))
        oor = int(((valid < lo) | (valid > hi)).sum())
        last = s.last_valid_index()
        stale_h = float((now - last).total_seconds() / 3600) if last is not None else np.inf
        # longest run of missing values
        na = s.isna().to_numpy()
        longest_gap = 0
        run = 0
        for v in na:
            run = run + 1 if v else 0
            longest_gap = max(longest_gap, run)
        optional = col == "ttf"
        status = "pass"
        if coverage < 0.9 or oor > 0 or (stale_h > 72 and col != "ttf"):
            status = "warn"
        if (coverage < 0.5 or oor > 0.01 * len(valid)) and not optional:
            status = "fail"
        if optional and coverage == 0:
            status = "warn"
        rank = {"pass": 0, "warn": 1, "fail": 2}
        if rank[status] > rank[worst] and not (optional and status == "warn"):
            worst = status
        checks.append(
            {
                "column": col,
                "coverage": round(coverage, 4),
                "out_of_range": oor,
                "longest_gap_h": int(longest_gap),
                "staleness_h": None if not np.isfinite(stale_h) else round(stale_h, 1),
                "optional": optional,
                "status": status,
            }
        )
    return {"status": worst, "checked_at": now.isoformat(), "checks": checks}
