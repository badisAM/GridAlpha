"""End-to-end: tiny synthetic pipeline run, then every API service."""
from __future__ import annotations

import pytest

GETS = [
    "/api/v1/health", "/api/v1/system/config", "/api/v1/market/summary", "/api/v1/market/prices?days=3",
    "/api/v1/market/daily", "/api/v1/market/profile", "/api/v1/forecast/latest", "/api/v1/forecast/explain",
    "/api/v1/forecast/history?days=3", "/api/v1/trading/plan", "/api/v1/backtest/summary",
    "/api/v1/backtest/equity", "/api/v1/backtest/daily", "/api/v1/backtest/monthly",
    "/api/v1/backtest/weights", "/api/v1/backtest/days", "/api/v1/models", "/api/v1/models/leaderboard",
    "/api/v1/models/error-by-hour", "/api/v1/models/calibration", "/api/v1/models/importance",
    "/api/v1/monitoring/drift", "/api/v1/monitoring/data-quality", "/api/v1/monitoring/latency",
    "/api/v1/monitoring/pipeline", "/api/v1/copilot/brief", "/api/v1/business/kpis",
    "/api/v1/pipeline/status",
]


def test_pipeline_succeeded(pipeline_run):
    assert pipeline_run["status"] == "success"
    assert pipeline_run["data_mode"] == "synthetic"
    assert set(pipeline_run["steps"]) >= {"ingest", "features", "backtest", "forecast", "optimise"}


@pytest.mark.parametrize("path", GETS)
def test_get_endpoints(client, path):
    r = client.get(path)
    assert r.status_code == 200, r.text
    assert "server-timing" in r.headers


def test_forecast_shape(client):
    d = client.get("/api/v1/forecast/latest").json()
    assert len(d["hours"]) in (23, 24, 25)
    h = d["hours"][0]
    assert h["ensemble_q10"] <= h["ensemble_q50"] <= h["ensemble_q90"]


def test_optimize_latest_and_past_day(client):
    r = client.post("/api/v1/trading/optimize", json={"day": "latest", "risk_aversion": 0.5})
    assert r.status_code == 200 and r.json()["status"] == "optimal"
    day = client.get("/api/v1/backtest/days").json()[-1]
    r = client.post("/api/v1/trading/optimize", json={"day": day, "power_mw": 5, "energy_mwh": 20})
    body = r.json()
    assert r.status_code == 200 and body["realised_pnl"] <= body["oracle_pnl"] + 1e-6


def test_validation_errors(client):
    assert client.post("/api/v1/trading/optimize", json={"rte": 3}).status_code == 422
    assert client.get("/api/v1/backtest/day/1999-01-01").status_code == 404


def test_copilot_and_investment(client):
    a = client.post("/api/v1/copilot/ask", json={"question": "when should I charge?"}).json()
    assert a["answer"] and a["grounded_on"] == "facts"
    inv = client.post("/api/v1/business/investment", json={"capex_eur_per_kwh": 150}).json()
    assert inv["capex_eur"] == 150 * 10 * 2 * 1000 and len(inv["cashflows"]) == 15


def test_websocket_replay(client):
    with client.websocket_connect("/ws/replay?speed=20") as ws:
        assert ws.receive_json()["type"] == "init"
        tick = ws.receive_json()
        assert tick["type"] == "tick" and tick["action"] in {"CHARGE", "DISCHARGE", "IDLE"}
