"""Trading Copilot: turns the numbers into a desk-ready morning brief.

Deterministic template by default (numbers are never hallucinated). If an
OpenAI-compatible endpoint is configured (Ollama, vLLM, OpenAI, Groq...),
the LLM only *rephrases* the structured facts; the facts block is always
returned alongside so the output stays auditable.
"""
from __future__ import annotations

import json

import httpx
import numpy as np
import pandas as pd

from ..config import get_settings
from ..log import get_logger
from ..timeutils import TZ, now_local

log = get_logger("copilot")

FEATURE_LABELS = {
    "res_proxy": "residual load (load − wind − solar)",
    "solar_proxy": "solar infeed forecast",
    "wind_proxy": "wind infeed forecast",
    "load_proxy": "demand forecast",
    "p_lag1d": "yesterday's price at the same hour",
    "p_d1_mean": "yesterday's average price",
    "p_hour_mean7": "7-day hourly price profile",
    "ttf_lag": "TTF gas price",
    "res_proxy_rank": "hour's rank in the residual-load curve",
    "res_proxy_day_mean": "daily mean residual load",
    "hour": "hour of day",
    "temp_fc": "temperature forecast",
    "clear_sky": "clear-sky solar geometry",
    "rad_s_fc": "solar radiation forecast",
    "wind100_n_fc": "100 m wind speed (north)",
    "doy_sin": "seasonality",
    "doy_cos": "seasonality",
    "p_lag7d": "last week's price at the same hour",
    "p_d1_std": "yesterday's price volatility",
    "res_act_lag48": "realised residual load (D-2)",
    "is_offday": "weekend / holiday",
    "ren_share_proxy": "renewable share forecast",
    "res_proxy_day_min": "daily minimum residual load",
    "res_proxy_day_max": "daily maximum residual load",
    "res_proxy_delta_d1": "residual load change vs yesterday",
    "cloud_fc": "cloud cover forecast",
    "wind_cf_fc": "wind capacity-factor forecast",
    "p_d1_max": "yesterday's maximum price",
    "p_d1_min": "yesterday's minimum price",
}


def _hours(ts: pd.Series) -> str:
    """Compress local hours into ranges: [11,12,13,17] -> '11–14h, 17–18h'."""
    hrs = sorted(set(pd.DatetimeIndex(ts).tz_convert(TZ).hour))
    if not hrs:
        return "—"
    out, start, prev = [], hrs[0], hrs[0]
    for h in hrs[1:] + [None]:
        if h is not None and h == prev + 1:
            prev = h
            continue
        out.append(f"{start:02d}–{prev + 1:02d}h")
        if h is not None:
            start = prev = h
    return ", ".join(out)


def build_facts(fc: pd.DataFrame, plan: pd.DataFrame, plan_meta: dict, drivers: list[dict],
                data_mode: str, drift: dict | None = None) -> dict:
    q50 = fc["q50"].to_numpy()
    width = (fc["q90"] - fc["q10"]).to_numpy()
    neg = fc[fc["q50"] < 0]
    low_band_neg = fc[fc["q10"] < 0]
    charge = plan[plan["charge"] > 0.05]
    discharge = plan[plan["discharge"] > 0.05]
    buy_px = float(np.average(charge["q50"], weights=charge["charge"])) if len(charge) else None
    sell_px = float(np.average(discharge["q50"], weights=discharge["discharge"])) if len(discharge) else None
    i_max, i_min = int(np.argmax(q50)), int(np.argmin(q50))
    ts_local = pd.DatetimeIndex(fc["ts"]).tz_convert(TZ)
    return {
        "delivery_day": str(ts_local[0].date()),
        "data_mode": data_mode,
        "base_price": round(float(q50.mean()), 1),
        "peak_price": round(float(q50[i_max]), 1),
        "peak_hour": f"{ts_local[i_max].hour:02d}h",
        "trough_price": round(float(q50[i_min]), 1),
        "trough_hour": f"{ts_local[i_min].hour:02d}h",
        "spread": round(float(q50.max() - q50.min()), 1),
        "negative_hours_expected": int(len(neg)),
        "negative_window": _hours(neg["ts"]) if len(neg) else None,
        "negative_risk_hours": int(len(low_band_neg)),
        "most_uncertain_hour": f"{ts_local[int(np.argmax(width))].hour:02d}h",
        "max_band_width": round(float(width.max()), 1),
        "charge_window": _hours(charge["ts"]) if len(charge) else None,
        "discharge_window": _hours(discharge["ts"]) if len(discharge) else None,
        "avg_buy_price": None if buy_px is None else round(buy_px, 1),
        "avg_sell_price": None if sell_px is None else round(sell_px, 1),
        "expected_pnl_eur": round(plan_meta.get("expected_pnl", 0.0), 0),
        "pnl_p5_eur": plan_meta.get("risk", {}).get("p5"),
        "pnl_cvar_eur": plan_meta.get("risk", {}).get("cvar"),
        "prob_loss": plan_meta.get("risk", {}).get("prob_loss"),
        "cycles": round(plan_meta.get("cycles", 0.0), 2),
        "drivers": drivers[:4],
        "drift_status": (drift or {}).get("status"),
    }


def alerts_from(facts: dict) -> list[dict]:
    a = []
    if facts["negative_hours_expected"] > 0:
        a.append({"level": "info", "code": "NEGATIVE_PRICES",
                  "message": f"{facts['negative_hours_expected']} h of negative prices expected "
                             f"({facts['negative_window']}) — the battery gets paid to charge."})
    elif facts["negative_risk_hours"] > 0:
        a.append({"level": "info", "code": "NEGATIVE_RISK",
                  "message": f"{facts['negative_risk_hours']} h have a >10 % chance of negative prices."})
    if facts["spread"] > 150:
        a.append({"level": "opportunity", "code": "WIDE_SPREAD",
                  "message": f"Wide intraday spread of {facts['spread']} €/MWh — high-value cycling day."})
    if facts["spread"] < 30:
        a.append({"level": "warning", "code": "FLAT_CURVE",
                  "message": f"Flat curve (spread {facts['spread']} €/MWh): cycling barely covers degradation."})
    if facts["max_band_width"] > 90:
        a.append({"level": "warning", "code": "HIGH_UNCERTAINTY",
                  "message": f"High uncertainty at {facts['most_uncertain_hour']} "
                             f"(P10–P90 band {facts['max_band_width']} €/MWh)."})
    if facts.get("drift_status") == "degraded":
        a.append({"level": "warning", "code": "MODEL_DRIFT",
                  "message": "Recent forecast error well above normal — retraining recommended."})
    elif facts.get("drift_status") == "watch":
        a.append({"level": "notice", "code": "MODEL_WATCH",
                  "message": "7-day forecast error slightly above its backtest average — monitoring."})
    if facts["data_mode"] != "live":
        a.append({"level": "notice", "code": "SIMULATED_DATA",
                  "message": "Running on the calibrated market simulator (public APIs unreachable)."})
    return a


def template_brief(facts: dict) -> str:
    drv = "; ".join(
        f"{FEATURE_LABELS.get(d['feature'], d['feature'])} ({d['impact_eur_mwh']:+.1f} €/MWh)"
        for d in facts["drivers"]
    )
    lines = [
        f"**Delivery {facts['delivery_day']} — base {facts['base_price']} €/MWh, "
        f"spread {facts['spread']} €/MWh.**",
        f"Peak {facts['peak_price']} €/MWh at {facts['peak_hour']}, trough {facts['trough_price']} €/MWh "
        f"at {facts['trough_hour']}.",
    ]
    if facts["charge_window"]:
        lines.append(
            f"Plan: charge {facts['charge_window']} (≈{facts['avg_buy_price']} €/MWh), discharge "
            f"{facts['discharge_window']} (≈{facts['avg_sell_price']} €/MWh), {facts['cycles']} cycles."
        )
    else:
        lines.append("Plan: stay idle — expected spread does not cover losses and degradation.")
    risk = ""
    if facts.get("pnl_p5_eur") is not None:
        risk = (f" 90 % of scenarios above {facts['pnl_p5_eur']:,.0f} €; "
                f"CVaR95 {facts['pnl_cvar_eur']:,.0f} €.")
    lines.append(f"Expected P&L {facts['expected_pnl_eur']:,.0f} €.{risk}")
    if drv:
        lines.append(f"Main drivers: {drv}.")
    return "\n".join(lines)


def llm_brief(facts: dict, draft: str) -> str | None:
    s = get_settings()
    if not s.llm_base_url:
        return None
    prompt = (
        "You are a senior power trader. Rewrite this day-ahead battery trading brief in 4-6 crisp "
        "sentences for the trading desk. Use ONLY the numbers in FACTS; do not invent numbers.\n\n"
        f"FACTS:\n{json.dumps(facts, default=str)}\n\nDRAFT:\n{draft}"
    )
    try:
        headers = {"Authorization": f"Bearer {s.llm_api_key}"} if s.llm_api_key else {}
        r = httpx.post(
            s.llm_base_url.rstrip("/") + "/chat/completions",
            json={"model": s.llm_model, "temperature": 0.2,
                  "messages": [{"role": "user", "content": prompt}]},
            headers=headers, timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        log.warning("LLM brief failed (%s) — using template", exc)
        return None


def generate(fc: pd.DataFrame, plan: pd.DataFrame, plan_meta: dict, drivers: list[dict],
             data_mode: str, drift: dict | None = None) -> dict:
    facts = build_facts(fc, plan, plan_meta, drivers, data_mode, drift)
    draft = template_brief(facts)
    text = llm_brief(facts, draft)
    return {
        "generated_at": now_local().isoformat(),
        "generated_by": f"llm:{get_settings().llm_model}" if text else "template",
        "text": text or draft,
        "facts": facts,
        "alerts": alerts_from(facts),
    }
