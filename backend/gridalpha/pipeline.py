"""End-to-end daily pipeline (what runs every morning before gate closure):

    ingest -> quality gate -> features -> walk-forward backtest -> train
    challenger -> registry (champion/challenger) -> forecast D+1 -> risk-aware
    bid -> monitoring -> copilot brief -> KPI report

Each step is timed and the run is appended to `pipeline_runs.jsonl`
(observable from the Monitoring page and the /monitoring/pipeline API).
"""
from __future__ import annotations

import time
import traceback
import uuid

import pandas as pd

from .backtest.engine import ENSEMBLE_MEMBERS, build_models, complete_days, run_backtest
from .backtest.report import write_markdown
from .config import get_settings
from .copilot.brief import generate as generate_brief
from .data.ingest import ingest
from .data.lake import get_lake
from .features.builder import build_features, day_rows, training_rows
from .log import get_logger, timed
from .models import registry
from .models.base import QCOLS
from .models.ensemble import AdaptiveConformal, combine
from .models.lgbm import global_shap_importance, top_drivers
from .monitoring.drift import data_drift, performance_drift
from .timeutils import now_local
from .trading.battery import BatterySpec
from .trading.planner import plan_day, risk_frontier

log = get_logger("pipeline")


def default_spec() -> BatterySpec:
    s = get_settings()
    return BatterySpec(
        power_mw=s.battery_power_mw, energy_mwh=s.battery_energy_mwh, rte=s.battery_rte,
        max_cycles_per_day=s.battery_max_cycles_per_day, soc_init_frac=s.battery_soc_init,
        degradation_eur_per_mwh=s.degradation_eur_per_mwh,
    )


def _target_day(feat: pd.DataFrame) -> pd.Timestamp:
    last = complete_days(feat)[-1]
    target = last + pd.Timedelta(days=1)
    rows = day_rows(feat, target)
    if rows.empty or rows["res_proxy"].isna().all():
        raise RuntimeError(f"no weather forecast available for target day {target.date()}")
    return target


def run_pipeline(mode: str | None = None, quick: bool = False, skip_backtest: bool = False) -> dict:
    s = get_settings()
    lake = get_lake()
    run = {"run_id": uuid.uuid4().hex[:10], "started_at": now_local().isoformat(),
           "quick": quick, "steps": {}, "status": "running"}
    t_start = time.perf_counter()
    steps = run["steps"]
    try:
        with timed(log, "ingest", steps):
            data_meta = ingest(mode)
        run["data_mode"] = data_meta["mode"]
        if data_meta["quality"]["status"] == "fail":
            raise RuntimeError("data-quality gate failed — see /monitoring/data-quality")

        with timed(log, "features", steps):
            feat = build_features(lake.read("market_hourly"))
            lake.write("features", feat)

        bt_models = None
        if skip_backtest and lake.exists("bt_daily"):
            summary = lake.read_json("bt_summary")
        else:
            with timed(log, "backtest", steps):
                bt = run_backtest(feat, days=90 if quick else None)
                lake.write("bt_forecasts", bt.forecasts)
                lake.write("bt_dispatch", bt.dispatch)
                lake.write("bt_daily", bt.daily)
                lake.write("bt_weights", bt.weights)
                lake.write_json("bt_summary", bt.summary)
                summary = bt.summary
                bt_models = bt.models

        with timed(log, "train_challenger", steps):
            target = _target_day(feat)
            # re-use the walk-forward experts: the deep model fine-tunes (warm start)
            models = bt_models or build_models()
            for m in models:
                m.fit(feat, target)
            version, vdir = registry.new_version_dir()
            for m in models:
                if m.name in ("lgbm", "tide"):
                    m.save(vdir)
            lgbm = next(m for m in models if m.name == "lgbm")
            fm = summary["forecast_metrics"].get("ensemble", {})
            tm = summary["trading_metrics"].get("ensemble_cvar", {})
            card = {
                "version": version, "created_at": now_local().isoformat(),
                "data_mode": data_meta["mode"], "train_until": str((target - pd.Timedelta(days=1)).date()),
                "period": summary["period"], "models": [m.name for m in models],
                "capture_ratio": tm.get("capture_ratio"), "mae": fm.get("mae"),
                "forecast_metrics": summary["forecast_metrics"],
                "trading_metrics": summary["trading_metrics"],
                "ensemble_weights": summary.get("latest_weights"),
                "tide_history": next((m.history for m in models if m.name == "tide"), None),
                "features": lgbm.features,
            }
            run["registry"] = registry.register(version, vdir, card)
            if not run["registry"]["promoted"]:
                # guard-rail: keep serving the champion's learned experts
                champs = {m.name: m for m in registry.load_champion_models()}
                models = [champs.get(m.name, m) for m in models]
                log.warning("challenger %s not promoted — forecasting with champion", version)
            served_version = registry.load_index()["champion"]

        with timed(log, "forecast", steps):
            preds = {m.name: m.predict(feat, [target]) for m in models}
            members = [n for n in ENSEMBLE_MEMBERS if n in preds and not preds[n].empty]
            w = {n: summary["latest_weights"].get(n, 0.0) for n in members}
            tot = sum(w.values()) or 1.0
            w = {n: v / tot for n, v in w.items()} if sum(w.values()) else {n: 1 / len(members) for n in members}
            raw = combine({n: preds[n] for n in members}, w)
            aci = AdaptiveConformal(s.conformal_target_coverage, s.conformal_gamma,
                                    summary.get("latest_conformal_log_scale", 0.0))
            preds["ensemble"] = aci.apply(raw)
            rows = day_rows(feat, target)
            long = []
            for n, p in preds.items():
                d = p.join(rows[["hour"]])
                d["model"] = n
                long.append(d)
            fc_long = pd.concat(long).rename_axis("ts").reset_index()
            lake.write("forecast_latest", fc_long)

            lgbm = next(m for m in models if m.name == "lgbm")
            drivers = top_drivers(lgbm, rows, k=6)
            shap = lgbm.shap(rows).drop(columns="_base")
            top_feats = shap.abs().mean().sort_values(ascending=False).index[:8]
            shap_hourly = shap[top_feats].round(2)
            shap_hourly["hour"] = rows["hour"].to_numpy()
            lake.write("shap_latest", shap_hourly.rename_axis("ts").reset_index())
            recent = training_rows(feat)
            recent = recent[recent["delivery_date"] > recent["delivery_date"].max() - pd.Timedelta(days=90)]
            imp = global_shap_importance(lgbm, recent)
            lake.write_json("forecast_meta", {
                "target_day": str(target.date()), "generated_at": now_local().isoformat(),
                "model_version": served_version, "ensemble_weights": w,
                "conformal_scale": aci.scale, "drivers": drivers,
                "global_importance": [{"feature": k, "share_pct": round(float(v), 2)}
                                      for k, v in imp.head(15).items()],
            })

        with timed(log, "optimise", steps):
            spec = default_spec()
            ens = fc_long[fc_long["model"] == "ensemble"].sort_values("ts")
            rho = float(summary.get("copula_rho", 0.85))
            plan, plan_meta = plan_day(ens[["ts", *QCOLS]], spec, s.risk_aversion, s.cvar_alpha,
                                       s.n_scenarios, rho)
            plan_meta["frontier"] = risk_frontier(ens[["ts", *QCOLS]], spec, s.cvar_alpha, rho)
            plan_meta["target_day"] = str(target.date())
            lake.write("plan_latest", plan)
            lake.write_json("plan_meta", plan_meta)

        with timed(log, "monitoring", steps):
            drift = {"data": data_drift(feat),
                     "performance": performance_drift(lake.read("bt_forecasts"))}
            lake.write_json("drift", drift)

        with timed(log, "copilot", steps):
            brief = generate_brief(ens, plan, plan_meta, drivers, data_meta["mode"],
                                   drift["performance"])
            lake.write_json("brief_latest", brief)

        run["status"] = "success"
        run["target_day"] = str(target.date())
    except Exception as exc:
        run["status"] = "failed"
        run["error"] = f"{type(exc).__name__}: {exc}"
        run["traceback"] = traceback.format_exc()[-2000:]
        log.error("pipeline failed: %s", exc)
        raise
    finally:
        run["finished_at"] = now_local().isoformat()
        run["duration_s"] = round(time.perf_counter() - t_start, 1)
        lake.append_jsonl("pipeline_runs", run)
        if run["status"] == "success":
            try:
                write_markdown(summary, card, data_meta)
            except Exception as exc:  # pragma: no cover
                log.warning("report generation failed: %s", exc)
    log.info("pipeline %s in %.1fs", run["status"], run["duration_s"])
    return run
