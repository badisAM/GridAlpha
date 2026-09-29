"""Business Objectives (BO) and Data-Science Objectives (DSO) scorecard.

Targets are fixed up-front (see docs/BUSINESS_CASE.md); achieved values are
recomputed from the latest walk-forward backtest on every pipeline run, so
the scorecard can never drift away from the code.
"""
from __future__ import annotations

from ..config import get_settings
from ..data.lake import get_lake
from ..timeutils import now_local

TRADE = "ensemble_cvar"
FCST = "ensemble"


def _status(ok: bool | None) -> str:
    return "n/a" if ok is None else ("pass" if ok else "miss")


def scorecard(summary: dict, runs: list[dict], latency: dict | None = None) -> dict:
    tm, fm = summary["trading_metrics"], summary["forecast_metrics"]
    best, naive, oracle = tm.get(TRADE, {}), tm.get("naive_d1", {}), tm.get("oracle", {})
    fe, fn = fm.get(FCST, {}), fm.get("naive_d1", {})
    s = get_settings()
    scale = s.battery_power_mw
    uplift_eur_year = (best.get("eur_per_mw_year", 0) - naive.get("eur_per_mw_year", 0)) * scale
    uplift_pct = (best.get("total_pnl_eur", 0) / naive.get("total_pnl_eur", 1) - 1) if naive else None
    mae_red = 1 - fe.get("mae", 0) / fn.get("mae", 1) if fn else None
    ok_runs = [r for r in runs if r.get("status") == "success"]
    dur = [r["duration_s"] for r in ok_runs if r.get("duration_s")]
    last_dur = dur[-1] if dur else None
    p95 = (latency or {}).get("p95_ms")

    bo = [
        {"id": "BO1", "objective": "Capture most of the theoretical arbitrage value",
         "kpi": "Capture ratio vs perfect foresight", "target": "≥ 85 % (stretch 90 %)",
         "value": best.get("capture_ratio"), "fmt": "pct",
         "status": _status(best.get("capture_ratio", 0) >= 0.85)},
        {"id": "BO2", "objective": "Beat the desk's current practice (naive D-1 schedule)",
         "kpi": f"Revenue uplift vs naive, € / year for {scale:g} MW", "target": "≥ +15 %",
         "value": uplift_pct, "fmt": "pct", "extra": round(uplift_eur_year, 0),
         "status": _status(uplift_pct is not None and uplift_pct >= 0.15)},
        {"id": "BO3", "objective": "Automate the daily bidding workflow end-to-end",
         "kpi": "Pipeline wall-clock (ingest → bid) / success rate", "target": "< 10 min / 100 %",
         "value": last_dur, "fmt": "seconds",
         "extra": round(len(ok_runs) / max(len(runs), 1), 3),
         "status": _status(None if last_dur is None else last_dur < 600)},
        {"id": "BO4", "objective": "Control downside risk",
         "kpi": "Share of loss-making days", "target": "≤ 2 %",
         "value": best.get("loss_day_share"), "fmt": "pct",
         "status": _status(best.get("loss_day_share", 1) <= 0.02)},
        {"id": "BO5", "objective": "Support the investment decision with measured revenue",
         "kpi": "Backtested revenue, € / MW / year", "target": "reported",
         "value": best.get("eur_per_mw_year"), "fmt": "eur", "extra": oracle.get("eur_per_mw_year"),
         "status": "pass" if best.get("eur_per_mw_year") else "n/a"},
    ]
    dso = [
        {"id": "DSO1", "objective": "Point accuracy", "kpi": "MAE reduction vs naive D-1",
         "target": "≥ 40 %", "value": mae_red, "fmt": "pct", "extra": fe.get("mae"),
         "status": _status(mae_red is not None and mae_red >= 0.40)},
        {"id": "DSO2", "objective": "Calibrated uncertainty", "kpi": "P10–P90 empirical coverage",
         "target": "75–85 %", "value": fe.get("coverage_80"), "fmt": "pct",
         "status": _status(0.75 <= fe.get("coverage_80", 0) <= 0.85)},
        {"id": "DSO3", "objective": "Rank the hours correctly (what a battery monetises)",
         "kpi": "Kendall τ per day (mean)", "target": "≥ 0.75", "value": fe.get("kendall_tau"),
         "fmt": "num", "extra": fn.get("kendall_tau"),
         "status": _status(fe.get("kendall_tau", 0) >= 0.75)},
        {"id": "DSO4", "objective": "Time the peak", "kpi": "Peak-hour hit rate (±1 h)",
         "target": "≥ 80 %", "value": fe.get("peak_hour_hit"), "fmt": "pct",
         "status": _status(fe.get("peak_hour_hit", 0) >= 0.80)},
        {"id": "DSO5", "objective": "Real-time serving", "kpi": "API p95 latency",
         "target": "< 150 ms", "value": p95, "fmt": "ms",
         "status": _status(None if p95 is None else p95 < 150)},
        {"id": "DSO6", "objective": "Fast decisions", "kpi": "MILP solve time (mean)",
         "target": "< 100 ms", "value": summary.get("avg_solve_ms"), "fmt": "ms",
         "status": _status(summary.get("avg_solve_ms", 1e9) < 100)},
    ]
    return {"generated_at": now_local().isoformat(), "period": summary["period"],
            "business_objectives": bo, "data_science_objectives": dso,
            "uplift_eur_per_year": round(uplift_eur_year, 0)}


def _fmt(v, fmt: str) -> str:
    if v is None:
        return "—"
    return {"pct": f"{v * 100:.1f} %", "eur": f"{v:,.0f} €", "ms": f"{v:.1f} ms",
            "seconds": f"{v:.0f} s", "num": f"{v:.3f}"}.get(fmt, str(v))


def _benchmark_latency() -> dict | None:
    p = get_settings().reports_dir / "benchmark.json"
    if not p.exists():
        return None
    import json

    return json.loads(p.read_text()).get("overall")


def write_markdown(summary: dict, card: dict, data_meta: dict) -> str:
    lake = get_lake()
    sc = scorecard(summary, lake.read_jsonl("pipeline_runs", 200), _benchmark_latency())
    tm, fm = summary["trading_metrics"], summary["forecast_metrics"]
    lines = [
        "# GridAlpha — KPI report (auto-generated)",
        "",
        f"*Generated {sc['generated_at'][:19]} · data mode: **{data_meta.get('mode')}** · "
        f"backtest {summary['period']['start']} → {summary['period']['end']} "
        f"({summary['period']['days']} days) · model version {card.get('version')}*",
        "",
        "## Scorecard",
        "",
        "| ID | Objective | KPI | Target | Achieved | Status |",
        "|---|---|---|---|---|---|",
    ]
    for r in sc["business_objectives"] + sc["data_science_objectives"]:
        lines.append(f"| {r['id']} | {r['objective']} | {r['kpi']} | {r['target']} | "
                     f"{_fmt(r['value'], r['fmt'])} | {r['status']} |")
    lines += ["", "## Trading performance (10 MW / 20 MWh unless configured otherwise)", "",
              "| Strategy | P&L € | €/MW/yr | Capture | Worst day € | CVaR5 day € | Loss days | Cycles/day |",
              "|---|---|---|---|---|---|---|---|"]
    for k in ("oracle", "ensemble_cvar", "ensemble", "lgbm", "tide", "profile7", "naive_d1"):
        if k in tm:
            v = tm[k]
            lines.append(f"| {k} | {v['total_pnl_eur']:,.0f} | {v['eur_per_mw_year']:,.0f} | "
                         f"{v['capture_ratio'] * 100:.1f} % | {v['worst_day_eur']:,.0f} | "
                         f"{v['cvar5_day_eur']:,.0f} | {v['loss_day_share'] * 100:.1f} % | "
                         f"{v['avg_cycles_per_day']:.2f} |")
    lines += ["", "## Forecast accuracy", "",
              "| Model | MAE | RMSE | Pinball | Coverage 80 % | Kendall τ | Peak-hour hit |",
              "|---|---|---|---|---|---|---|"]
    for k in ("ensemble", "lgbm", "tide", "profile7", "naive_d1", "naive_d7"):
        if k in fm:
            v = fm[k]
            lines.append(f"| {k} | {v['mae']:.2f} | {v['rmse']:.2f} | {v['pinball']:.2f} | "
                         f"{v['coverage_80'] * 100:.1f} % | {v['kendall_tau']:.3f} | "
                         f"{v['peak_hour_hit'] * 100:.0f} % |")
    lines += ["", f"Timings: {summary.get('timings_s')} · mean MILP solve "
              f"{summary.get('avg_solve_ms')} ms", ""]
    md = "\n".join(lines)
    out = get_settings().reports_dir / "kpi_report.md"
    out.write_text(md, encoding="utf-8")
    return md
