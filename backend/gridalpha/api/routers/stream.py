"""Real-time channel (WebSocket): market replay of the last backtest week.

Streams one delivery hour per tick: realised price, forecast band, the
committed battery action, state of charge and running P&L of the AI
strategy vs the naive desk — the "live trading desk" view. It replays
settled history (clearly labelled), it is not a live exchange feed.
"""
from __future__ import annotations

import asyncio

import numpy as np
import pandas as pd
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ...data.lake import get_lake
from ...timeutils import TZ

router = APIRouter()


def _frames(days: int = 7) -> list[dict]:
    lake = get_lake()
    disp = lake.read("bt_dispatch")
    fc = lake.read("bt_forecasts")
    last = disp["delivery_date"].max()
    disp = disp[disp["delivery_date"] > last - pd.Timedelta(days=days)]
    fc = fc[(fc["model"] == "ensemble") & (fc["delivery_date"] > last - pd.Timedelta(days=days))]
    fc = fc.set_index("ts")[["q10", "q50", "q90"]]
    ai = disp[disp["strategy"] == "ensemble_cvar"].set_index("ts").sort_index()
    nv = disp[disp["strategy"] == "naive_d1"].set_index("ts").sort_index()
    deg = float((lake.read_json("bt_summary") or {}).get("battery", {}).get("degradation_eur_per_mwh", 8.0))
    pnl_ai = ((ai["discharge"] - ai["charge"]) * ai["price"] - deg * ai["discharge"]).cumsum()
    pnl_nv = ((nv["discharge"] - nv["charge"]) * nv["price"] - deg * nv["discharge"]).cumsum()
    out = []
    for ts, r in ai.iterrows():
        q = fc.loc[ts] if ts in fc.index else None
        net = float(r["discharge"] - r["charge"])
        out.append({
            "ts": ts.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
            "local": ts.tz_convert(TZ).strftime("%a %d %b %H:%M"),
            "price": round(float(r["price"]), 2),
            "q10": None if q is None else round(float(q["q10"]), 2),
            "q50": None if q is None else round(float(q["q50"]), 2),
            "q90": None if q is None else round(float(q["q90"]), 2),
            "action": "DISCHARGE" if net > 0.05 else "CHARGE" if net < -0.05 else "IDLE",
            "mw": round(abs(net), 2),
            "soc": round(float(r["soc"]), 2),
            "pnl_ai": round(float(pnl_ai.loc[ts]), 0),
            "pnl_naive": round(float(pnl_nv.loc[ts]), 0) if ts in pnl_nv.index else None,
        })
    return out


@router.websocket("/ws/replay")
async def replay(ws: WebSocket, speed: float = 4.0) -> None:
    await ws.accept()
    try:
        frames = await asyncio.to_thread(_frames)
    except FileNotFoundError:
        await ws.send_json({"error": "no backtest yet — run the pipeline"})
        await ws.close()
        return
    delay = 1.0 / float(np.clip(speed, 0.5, 20))
    try:
        await ws.send_json({"type": "init", "n": len(frames)})
        i = 0
        while True:
            await ws.send_json({"type": "tick", "i": i % len(frames), **frames[i % len(frames)]})
            i += 1
            await asyncio.sleep(delay)
    except (WebSocketDisconnect, RuntimeError):
        return
