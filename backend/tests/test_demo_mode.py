"""Public-demo mode: the API serves the snapshot and refuses pipeline runs."""
from fastapi.testclient import TestClient


def test_pipeline_api_can_be_disabled(monkeypatch, pipeline_run):
    from gridalpha.api.main import create_app
    from gridalpha.config import get_settings

    monkeypatch.setenv("GRIDALPHA_PIPELINE_API_ENABLED", "false")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as c:
            assert c.get("/api/v1/health").json()["pipeline_enabled"] is False
            r = c.post("/api/v1/pipeline/run", json={"quick": True})
            assert r.status_code == 403
            assert "disabled" in r.json()["detail"]
    finally:
        monkeypatch.delenv("GRIDALPHA_PIPELINE_API_ENABLED")
        get_settings.cache_clear()


def test_pipeline_api_enabled_by_default(client):
    assert client.get("/api/v1/health").json()["pipeline_enabled"] is True