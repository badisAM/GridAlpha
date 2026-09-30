"""System service: health, config, pipeline orchestration."""
from __future__ import annotations

import threading

from fastapi import APIRouter, HTTPException

from ... import __version__
from ...config import get_settings
from ...data.lake import get_lake
from ...log import get_logger
from ...models import registry
from ..schemas import PipelineRequest

router = APIRouter(tags=["system"])
log = get_logger("api.system")

_run_lock = threading.Lock()
_state = {"running": False, "request": None}


@router.get("/health")
def health() -> dict:
    lake = get_lake()
    runs = lake.read_jsonl("pipeline_runs", 1)
    meta = lake.read_json("data_meta") or {}
    fmeta = lake.read_json("forecast_meta") or {}
    return {
        "status": "ok" if lake.exists("plan_latest") else "needs_pipeline_run",
        "version": __version__,
        "data_mode": meta.get("mode"),
        "model_version": registry.load_index().get("champion"),
        "target_day": fmeta.get("target_day"),
        "last_run": {k: runs[-1].get(k) for k in ("run_id", "status", "finished_at", "duration_s")} if runs else None,
        "pipeline_running": _state["running"],
        "pipeline_enabled": get_settings().pipeline_api_enabled,
    }


@router.get("/system/config")
def config() -> dict:
    s = get_settings()
    return {
        "bidding_zone": s.bidding_zone, "timezone": s.timezone, "data_mode": s.data_mode,
        "quantiles": s.quantiles, "backtest_days": s.backtest_days,
        "retrain_every_days": s.retrain_every_days, "deep_model": s.enable_deep_model,
        "battery": {"power_mw": s.battery_power_mw, "energy_mwh": s.battery_energy_mwh,
                    "rte": s.battery_rte, "max_cycles_per_day": s.battery_max_cycles_per_day,
                    "degradation_eur_per_mwh": s.degradation_eur_per_mwh,
                    "soc_init_frac": s.battery_soc_init},
        "risk": {"risk_aversion": s.risk_aversion, "cvar_alpha": s.cvar_alpha,
                 "n_scenarios": s.n_scenarios},
        "scheduler": {"enabled": s.scheduler_enabled,
                      "time": f"{s.scheduler_hour:02d}:{s.scheduler_minute:02d} {s.timezone}"},
        "llm_copilot": bool(s.llm_base_url),
    }


def _run(req: PipelineRequest) -> None:
    from ...pipeline import run_pipeline

    try:
        run_pipeline(mode=req.mode, quick=req.quick)
    except Exception as exc:
        log.error("pipeline run from API failed: %s", exc)
    finally:
        _state["running"] = False
        _run_lock.release()


@router.post("/pipeline/run", status_code=202)
def trigger(req: PipelineRequest) -> dict:
    if not get_settings().pipeline_api_enabled:
        raise HTTPException(
            403,
            "Pipeline runs are disabled on this public demo (read-only snapshot of real market data). "
            "Run it locally: python -m gridalpha.cli run",
        )
    if not _run_lock.acquire(blocking=False):
        raise HTTPException(409, "a pipeline run is already in progress")
    _state.update(running=True, request=req.model_dump())
    threading.Thread(target=_run, args=(req,), daemon=True, name="pipeline").start()
    return {"accepted": True, **req.model_dump()}


@router.get("/pipeline/status")
def status() -> dict:
    runs = get_lake().read_jsonl("pipeline_runs", 5)
    for r in runs:
        r.pop("traceback", None)
    return {"running": _state["running"], "request": _state["request"], "recent": runs[::-1]}
