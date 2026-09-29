"""Test fixtures: an isolated lake + a tiny end-to-end pipeline run."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="gridalpha-test-"))
os.environ.update({
    "GRIDALPHA_DATA_MODE": "synthetic",
    "GRIDALPHA_DATA_DIR": str(_TMP / "data"),
    "GRIDALPHA_ARTIFACTS_DIR": str(_TMP / "artifacts"),
    "GRIDALPHA_HISTORY_START": "2025-01-01",
    "GRIDALPHA_BACKTEST_DAYS": "14",
    "GRIDALPHA_RETRAIN_EVERY_DAYS": "14",
    "GRIDALPHA_ENABLE_DEEP_MODEL": "false",
})


@pytest.fixture(scope="session")
def pipeline_run():
    from gridalpha.config import get_settings
    from gridalpha.data import lake as lake_mod

    get_settings.cache_clear()
    lake_mod._LAKE = None
    from gridalpha.pipeline import run_pipeline

    return run_pipeline(mode="synthetic")


@pytest.fixture(scope="session")
def client(pipeline_run):
    from fastapi.testclient import TestClient

    from gridalpha.api.main import create_app

    with TestClient(create_app()) as c:
        yield c
