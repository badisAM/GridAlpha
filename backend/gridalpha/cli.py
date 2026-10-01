"""Command-line entry point.

    python -m gridalpha.cli run            # full pipeline (365-day backtest)
    python -m gridalpha.cli run --quick    # 90-day backtest, ~2 min
    python -m gridalpha.cli ingest --mode synthetic
    python -m gridalpha.cli serve          # FastAPI on :8000
    python -m gridalpha.cli schedule       # daily job at 10:30 Europe/Berlin
"""
from __future__ import annotations

import json

import typer

from .log import get_logger, setup_logging

app = typer.Typer(add_completion=False, help="GridAlpha - AI battery trading copilot")
log = get_logger("cli")


@app.command()
def run(
    quick: bool = typer.Option(False, help="90-day backtest instead of 365 days"),
    mode: str = typer.Option(None, help="auto | live | synthetic"),
    skip_backtest: bool = typer.Option(False, help="reuse the last backtest"),
    forecast_only: bool = typer.Option(
        False, help="daily refresh: new data + saved champion -> plan for D+1 (no backtest, no retraining)"),
) -> None:
    """Run the full daily pipeline."""
    from .pipeline import run_pipeline

    res = run_pipeline(mode=mode, quick=quick, skip_backtest=skip_backtest, forecast_only=forecast_only)
    typer.echo(json.dumps({k: res[k] for k in ("run_id", "status", "data_mode", "target_day",
                                                "duration_s", "steps") if k in res}, indent=2))


@app.command()
def ingest(mode: str = typer.Option(None, help="auto | live | synthetic")) -> None:
    """Scrape / simulate market data into the lake only."""
    from .data.ingest import ingest as _ingest

    meta = _ingest(mode)
    typer.echo(json.dumps({k: meta[k] for k in ("mode", "rows", "last_price_ts")}, indent=2))


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> None:
    """Start the REST + WebSocket API."""
    import uvicorn

    uvicorn.run("gridalpha.api.main:app", host=host, port=port, reload=reload)


@app.command()
def schedule() -> None:
    """Blocking scheduler: runs the pipeline every day before gate closure."""
    from .scheduler import run_forever

    run_forever()


@app.command()
def report(refresh: bool = typer.Option(False, help="re-render from the lake (e.g. after a benchmark)")) -> None:
    """Print the KPI scorecard of the latest backtest."""
    from .config import get_settings

    if refresh:
        from .backtest.report import write_markdown
        from .data.lake import get_lake
        from .models import registry

        lake = get_lake()
        write_markdown(lake.read_json("bt_summary"), registry.card() or {}, lake.read_json("data_meta") or {})
    p = get_settings().reports_dir / "kpi_report.md"
    typer.echo(p.read_text(encoding="utf-8") if p.exists() else "no report yet - run the pipeline")


if __name__ == "__main__":
    setup_logging()
    app()
