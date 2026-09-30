"""File-based model registry (versioned artefacts + metadata + champion tag).

Each pipeline run writes `artifacts/models/<version>/` with the trained
boosters / network weights and a `card.json` (data window, data mode,
backtest metrics, feature list). The newest version is promoted to
*champion* only if it does not degrade the backtest capture ratio by more
than 2 points versus the current champion (simple guard-rail against a bad
retrain). MLflow logging is optional (`pip install mlflow`,
`MLFLOW_TRACKING_URI=...`).
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from ..config import get_settings
from ..log import get_logger
from ..timeutils import now_local

log = get_logger("registry")
KEEP_VERSIONS = 5


def _index_path() -> Path:
    return get_settings().models_dir / "registry.json"


def load_index() -> dict:
    p = _index_path()
    if not p.exists():
        return {"champion": None, "versions": []}
    return json.loads(p.read_text(encoding="utf-8-sig"))


def _save_index(idx: dict) -> None:
    p = _index_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(idx, indent=2, default=str))
    os.replace(tmp, p)


def new_version_dir() -> tuple[str, Path]:
    version = now_local().strftime("v%Y%m%d-%H%M%S")
    path = get_settings().models_dir / version
    path.mkdir(parents=True, exist_ok=True)
    return version, path


def _overlap(a: dict | None, b: dict | None) -> float:
    """Share of backtest days two evaluation windows have in common."""
    if not a or not b:
        return 0.0
    from datetime import date

    a0, a1 = date.fromisoformat(a["start"]), date.fromisoformat(a["end"])
    b0, b1 = date.fromisoformat(b["start"]), date.fromisoformat(b["end"])
    inter = (min(a1, b1) - max(a0, b0)).days + 1
    union = (max(a1, b1) - min(a0, b0)).days + 1
    return max(0.0, inter / union)


def register(version: str, path: Path, card: dict) -> dict:
    """Champion/challenger: the challenger is promoted unless it is evaluated on
    (almost) the same backtest window as the champion AND loses > 2 pts of
    capture ratio. When windows differ (new data, other horizon) the most
    recent evaluation wins."""
    (path / "card.json").write_text(json.dumps(card, indent=2, default=str))
    idx = load_index()
    champ = next((v for v in idx["versions"] if v["version"] == idx.get("champion")), None)
    comparable = champ is not None and _overlap(champ.get("period"), card.get("period")) >= 0.8
    promote = (not comparable) or (card.get("capture_ratio") or 0) >= (champ.get("capture_ratio") or 0) - 0.02
    idx["versions"].append({"version": version, "path": str(path), "promoted": promote, **{
        k: card.get(k) for k in ("created_at", "data_mode", "train_until", "models", "capture_ratio",
                                 "mae", "period")}})
    if promote:
        idx["champion"] = version
    log.info("registered %s (promoted=%s, comparable=%s)", version, promote, comparable)
    # retention
    while len(idx["versions"]) > KEEP_VERSIONS:
        old = idx["versions"].pop(0)
        if old["version"] != idx["champion"]:
            shutil.rmtree(get_settings().models_dir / old["version"], ignore_errors=True)
    _save_index(idx)
    _maybe_mlflow(version, card)
    return {"version": version, "promoted": promote}


def _maybe_mlflow(version: str, card: dict) -> None:
    if not os.environ.get("MLFLOW_TRACKING_URI"):
        return
    try:
        import mlflow

        mlflow.set_experiment("gridalpha")
        with mlflow.start_run(run_name=version):
            mlflow.log_params({"data_mode": card.get("data_mode"), "train_until": card.get("train_until")})
            for model, m in (card.get("forecast_metrics") or {}).items():
                for k in ("mae", "rmse", "pinball", "coverage_80", "kendall_tau"):
                    if m.get(k) is not None:
                        mlflow.log_metric(f"{model}.{k}", m[k])
    except Exception as exc:  # pragma: no cover - optional integration
        log.warning("mlflow logging skipped: %s", exc)


def load_champion_models() -> list:
    """Load the champion's learned experts (LightGBM, TiDE) from disk."""
    p = champion_path()
    out = []
    if p is None:
        return out
    from .lgbm import LGBMQuantile

    if (p / "lgbm_meta.json").exists():
        out.append(LGBMQuantile.load(p))
    if (p / "tide_meta.json").exists():
        try:
            from .tide import TORCH_OK, TiDEQuantile

            if TORCH_OK:
                out.append(TiDEQuantile.load(p))
        except Exception as exc:  # pragma: no cover
            log.warning("could not load champion TiDE: %s", exc)
    return out


def champion_path() -> Path | None:
    idx = load_index()
    for v in idx["versions"]:
        if v["version"] == idx.get("champion"):
            return get_settings().models_dir / v["version"]
    return None


def card(version: str | None = None) -> dict | None:
    idx = load_index()
    version = version or idx.get("champion")
    for v in idx["versions"]:
        if v["version"] == version:
            p = get_settings().models_dir / v["version"] / "card.json"
            return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else None
    return None


def stamp() -> str:
    return now_local().isoformat()
