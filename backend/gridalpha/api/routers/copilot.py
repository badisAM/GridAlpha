"""Copilot service: morning brief + grounded Q&A over today's facts."""
from __future__ import annotations

import json
import re

import httpx
from fastapi import APIRouter

from ...config import get_settings
from ..deps import require_json
from ..schemas import AskRequest

router = APIRouter(prefix="/copilot", tags=["copilot"])


@router.get("/brief")
def brief() -> dict:
    return require_json("brief_latest")


INTENTS = [
    (r"charg|buy|achet|recharg", lambda f: f"Charge {f['charge_window'] or 'no hours'} at ≈{f['avg_buy_price']} €/MWh."),
    (r"dischar|sell|vend|décharg|decharg", lambda f: f"Discharge {f['discharge_window'] or 'no hours'} at ≈{f['avg_sell_price']} €/MWh."),
    (r"negat|négat", lambda f: (f"{f['negative_hours_expected']} h expected below 0 €/MWh ({f['negative_window']})."
                               if f["negative_hours_expected"] else
                               f"No negative hour expected; {f['negative_risk_hours']} h have >10 % risk.")),
    (r"risk|risque|cvar|loss|perte", lambda f: (f"Expected P&L {f['expected_pnl_eur']:,.0f} €, 5th percentile "
                                                f"{(f['pnl_p5_eur'] or 0):,.0f} €, CVaR95 {(f['pnl_cvar_eur'] or 0):,.0f} €, "
                                                f"probability of loss {(f['prob_loss'] or 0) * 100:.0f} %.")),
    (r"peak|pic|max|expensive|cher", lambda f: f"Peak {f['peak_price']} €/MWh at {f['peak_hour']}."),
    (r"trough|creux|min|cheap", lambda f: f"Trough {f['trough_price']} €/MWh at {f['trough_hour']}."),
    (r"why|pourquoi|driver|explain|expli", lambda f: "Main drivers: " + "; ".join(
        f"{d['feature']} ({d['impact_eur_mwh']:+.1f} €/MWh)" for d in f["drivers"]) + "."),
    (r"spread|écart|ecart", lambda f: f"Expected intraday spread {f['spread']} €/MWh."),
    (r"pnl|p&l|profit|gain|revenu|money|argent", lambda f: f"Expected P&L {f['expected_pnl_eur']:,.0f} € for {f['cycles']} cycles."),
]


@router.post("/ask")
def ask(req: AskRequest) -> dict:
    """Answers are grounded in the structured facts of the latest brief.
    With an LLM configured the model answers from the facts only."""
    b = require_json("brief_latest")
    facts = b["facts"]
    s = get_settings()
    if s.llm_base_url:
        try:
            headers = {"Authorization": f"Bearer {s.llm_api_key}"} if s.llm_api_key else {}
            r = httpx.post(s.llm_base_url.rstrip("/") + "/chat/completions", headers=headers, timeout=30,
                           json={"model": s.llm_model, "temperature": 0.1, "messages": [
                               {"role": "system", "content": "You are a power-trading copilot. Answer in 1-3 "
                                "sentences using ONLY these facts; say so if the facts do not cover it.\n"
                                + json.dumps(facts, default=str)},
                               {"role": "user", "content": req.question}]})
            r.raise_for_status()
            return {"answer": r.json()["choices"][0]["message"]["content"].strip(),
                    "grounded_on": "facts", "engine": f"llm:{s.llm_model}"}
        except Exception:
            pass
    q = req.question.lower()
    answers = [fn(facts) for pat, fn in INTENTS if re.search(pat, q)]
    if not answers:
        answers = [b["text"].split("\n")[0].replace("**", "")]
    return {"answer": " ".join(answers), "grounded_on": "facts", "engine": "rules"}
