"""API latency benchmark: N sequential requests per endpoint, p50/p95/p99.

    python scripts/benchmark.py [--base http://127.0.0.1:8000] [-n 200]

Writes backend/artifacts/reports/benchmark.json (read by the KPI scorecard).
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import httpx

GETS = ["/health", "/market/summary", "/market/prices?days=14", "/forecast/latest", "/forecast/explain",
        "/trading/plan", "/backtest/summary", "/backtest/equity", "/models/leaderboard",
        "/monitoring/drift", "/copilot/brief", "/business/kpis"]
POSTS = [("/trading/optimize", {"day": "latest", "risk_aversion": 0.1}),
         ("/trading/optimize", {"day": "latest", "risk_aversion": 0.0, "power_mw": 50, "energy_mwh": 200})]


def pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("-n", type=int, default=200)
    a = ap.parse_args()
    api = a.base.rstrip("/") + "/api/v1"
    rows, allv = [], []
    with httpx.Client(timeout=30) as c:
        for path in GETS:
            c.get(api + path).raise_for_status()  # warm cache
            ts = []
            for _ in range(a.n):
                t0 = time.perf_counter(); r = c.get(api + path); ts.append((time.perf_counter() - t0) * 1000)
                r.raise_for_status()
            rows.append({"route": f"GET {path}", "p50_ms": pct(ts, .5), "p95_ms": pct(ts, .95), "p99_ms": pct(ts, .99)})
            allv += ts
        for path, body in POSTS:
            ts = []
            for _ in range(max(20, a.n // 5)):
                t0 = time.perf_counter(); r = c.post(api + path, json=body); ts.append((time.perf_counter() - t0) * 1000)
                r.raise_for_status()
            label = "CVaR λ=0.1, 100 scenarios" if body.get("risk_aversion") else "risk-neutral, 50 MW"
            rows.append({"route": f"POST {path} ({label})", "p50_ms": pct(ts, .5),
                         "p95_ms": pct(ts, .95), "p99_ms": pct(ts, .99), "solver": True})
    reads = [x for r in rows if not r.get("solver") for x in [r["p95_ms"]]]
    overall = {"count": len(allv), "p50_ms": round(statistics.median(allv), 2),
               "p95_ms": round(pct(allv, .95), 2), "p99_ms": round(pct(allv, .99), 2),
               "scope": "read endpoints (client-side, sequential, cached)"}
    for r in rows:
        print(f"{r['route']:48s} p50 {r['p50_ms']:7.2f} ms   p95 {r['p95_ms']:7.2f} ms   p99 {r['p99_ms']:7.2f} ms")
    print("overall read p50 %.2f ms · p95 %.2f ms · p99 %.2f ms" % (overall["p50_ms"], overall["p95_ms"], overall["p99_ms"]))
    out = Path(__file__).resolve().parents[1] / "backend" / "artifacts" / "reports" / "benchmark.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"overall": overall, "routes": rows, "max_read_p95_ms": max(reads)}, indent=2))
    print("wrote", out)


if __name__ == "__main__":
    main()
