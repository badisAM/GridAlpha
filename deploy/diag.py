import io, json, os, platform, sys, traceback
from pathlib import Path

SPACE_URL = "https://bedis123-gridalpha-api.hf.space"
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
out = io.StringIO()

def say(*a):
    line = " ".join(str(x) for x in a)
    print(line)
    out.write(line + "\n")

def section(t):
    say(""); say("=" * 70); say(t); say("=" * 70)

def main():
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "space-build").resolve()
    if not (target / "gridalpha").is_dir():
        say("ERROR: no 'gridalpha' folder in", target); return 1
    data, arts = target / "data", target / "artifacts"
    os.environ["GRIDALPHA_DATA_MODE"] = "live"
    os.environ["GRIDALPHA_DATA_DIR"] = str(data)
    os.environ["GRIDALPHA_ARTIFACTS_DIR"] = str(arts)
    sys.path.insert(0, str(target))

    section("1. ENVIRONMENT")
    say("python:", sys.version.split()[0], platform.platform())
    for pkg in ("fastapi", "starlette", "pandas", "pyarrow", "duckdb", "lightgbm", "torch", "httpx"):
        try:
            say(f"  {pkg:10s}", getattr(__import__(pkg), "__version__", "?"))
        except Exception as exc:
            say(f"  {pkg:10s} MISSING ({exc})")

    section("2. SNAPSHOT INVENTORY")
    for folder in (data / "lake", arts / "models"):
        say(f"[{folder.relative_to(target)}]")
        if not folder.exists():
            say("   !! folder missing"); continue
        for p in sorted(folder.rglob("*")):
            if p.is_file():
                say(f"   {p.stat().st_size/1024:9.1f} KB  {p.relative_to(folder)}")
    reg = arts / "models" / "registry.json"
    try:
        idx = json.loads(reg.read_text(encoding="utf-8-sig"))
        champ = idx.get("champion")
        say("champion:", champ, "| versions:", [v.get("version") for v in idx.get("versions", [])])
        say("champion folder exists:", (arts / "models" / str(champ)).is_dir())
    except Exception as exc:
        say("registry.json problem:", repr(exc))

    section("3. METADATA FILES (BOM / invalid JSON)")
    bad = 0
    for p in sorted(list(data.rglob("*.json")) + list(data.rglob("*.jsonl")) + list(arts.rglob("*.json"))):
        if "raw" in p.parts:
            continue
        b = p.read_bytes(); issues = []
        if b.startswith(b"\xef\xbb\xbf"): issues.append("BOM")
        if b.startswith(b"\xff\xfe") or b.startswith(b"\xfe\xff"): issues.append("UTF-16 !!")
        try:
            txt = b.decode("utf-8-sig")
            if p.suffix == ".jsonl":
                for line in txt.splitlines():
                    if line.strip(): json.loads(line)
            else:
                json.loads(txt)
        except Exception as exc:
            issues.append(f"INVALID JSON: {exc}")
        if issues:
            bad += 1; say(f"  !! {p.relative_to(target)} -> {', '.join(issues)}")
    say(f"  {bad} problematic file(s)")

    section("4. API - LOCAL (same code + same data as the Space)")
    try:
        from fastapi.testclient import TestClient
        import gridalpha
        say("gridalpha imported from:", Path(gridalpha.__file__).parent)
        from gridalpha.api.main import app
        client = TestClient(app, raise_server_exceptions=True)
    except Exception:
        say("!! cannot import the API:"); say(traceback.format_exc()); return 1
    fails = 0
    for path in GETS:
        try:
            r = client.get(path); say(f"  {r.status_code}  {path}")
            if r.status_code >= 400:
                fails += 1; say("       ", r.text[:300])
        except Exception:
            fails += 1; say(f"  EXC  {path}")
            say("       " + traceback.format_exc().replace("\n", "\n       "))
    say(f"  -> {fails} failing endpoint(s) locally")

    section(f"5. API - DEPLOYED SPACE ({SPACE_URL})")
    try:
        import httpx
        with httpx.Client(timeout=60, follow_redirects=True) as http:
            for path in GETS:
                try:
                    r = http.get(SPACE_URL + path)
                    say(f"  {r.status_code}  {path}" + ("" if r.status_code < 400 else f"   {r.text[:120]!r}"))
                except Exception as exc:
                    say(f"  ERR  {path}  {exc!r}")
    except Exception as exc:
        say("remote check skipped:", repr(exc))
    return 0

if __name__ == "__main__":
    code = 1
    try:
        code = main()
    finally:
        rep = Path(__file__).with_name("diag_report.txt")
        rep.write_text(out.getvalue(), encoding="utf-8")
        print(f"\nReport written to {rep}")
    sys.exit(code)