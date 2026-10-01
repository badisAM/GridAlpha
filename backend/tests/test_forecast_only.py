"""Daily refresh: fresh data + the saved champion forecast D+1 without
re-running the backtest or registering a new model version."""


def test_forecast_only_reuses_champion(pipeline_run):
    from gridalpha.data.lake import get_lake
    from gridalpha.models import registry
    from gridalpha.pipeline import run_pipeline

    lake = get_lake()
    versions_before = len(registry.load_index()["versions"])
    champion = registry.load_index()["champion"]
    bt_before = lake.read_json("bt_summary")

    run = run_pipeline(mode="synthetic", forecast_only=True)

    assert run["status"] == "success"
    assert run["forecast_only"] is True
    assert "backtest" not in run["steps"] and "train_challenger" not in run["steps"]
    assert run["registry"] == {"version": champion, "promoted": False, "reused": True}
    assert len(registry.load_index()["versions"]) == versions_before
    assert lake.read_json("bt_summary") == bt_before
    assert lake.read_json("forecast_meta")["model_version"] == champion
    assert lake.exists("plan_latest")
