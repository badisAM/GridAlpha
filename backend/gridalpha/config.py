"""Central configuration (12-factor): every value can be overridden with a
GRIDALPHA_* environment variable or a `.env` file at the repo root."""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GRIDALPHA_",
        env_file=(str(REPO_DIR / ".env"), str(BACKEND_DIR / ".env")),
        extra="ignore",
    )

    # ---- data -------------------------------------------------------------
    # auto      : try the public APIs, fall back to the calibrated simulator
    # live      : public APIs only (fails loudly if unreachable)
    # synthetic : calibrated market simulator only (offline demo / CI)
    data_mode: Literal["auto", "live", "synthetic"] = "auto"
    bidding_zone: str = "DE-LU"
    country: str = "de"
    timezone: str = "Europe/Berlin"
    history_start: date = date(2023, 1, 1)
    data_dir: Path = BACKEND_DIR / "data"
    artifacts_dir: Path = BACKEND_DIR / "artifacts"
    http_timeout_s: float = 30.0

    # ---- modelling ----------------------------------------------------------
    quantiles: tuple[float, float, float] = (0.1, 0.5, 0.9)
    backtest_days: int = 365
    retrain_every_days: int = 28
    enable_deep_model: bool = True
    tide_epochs: int = 160
    ensemble_window_days: int = 28
    ensemble_temperature: float = 0.05
    tide_seeds: int = 2
    conformal_target_coverage: float = 0.8
    conformal_gamma: float = 0.05
    seed: int = 42

    # ---- battery asset (default: 10 MW / 20 MWh utility-scale BESS) --------
    battery_power_mw: float = 10.0
    battery_energy_mwh: float = 20.0
    battery_rte: float = 0.88
    battery_max_cycles_per_day: float = 1.5
    battery_soc_init: float = 0.5
    degradation_eur_per_mwh: float = 8.0
    n_scenarios: int = 100
    cvar_alpha: float = 0.95
    risk_aversion: float = 0.1  # knee of the backtest risk/return frontier

    # ---- serving ------------------------------------------------------------
    api_cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    scheduler_enabled: bool = False
    # public demo (e.g. Hugging Face ZeroGPU Space): serve a data snapshot and
    # refuse pipeline runs from the API (no retraining inside the web process)
    pipeline_api_enabled: bool = True
    scheduler_hour: int = 10
    scheduler_minute: int = 30

    # ---- optional LLM copilot (any OpenAI-compatible endpoint, e.g. Ollama) --
    llm_base_url: str | None = None  # e.g. http://localhost:11434/v1
    llm_model: str = "llama3.1"
    llm_api_key: str | None = None

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def lake_dir(self) -> Path:
        return self.data_dir / "lake"

    @property
    def models_dir(self) -> Path:
        return self.artifacts_dir / "models"

    @property
    def reports_dir(self) -> Path:
        return self.artifacts_dir / "reports"

    def ensure_dirs(self) -> None:
        for p in (self.raw_dir, self.lake_dir, self.models_dir, self.reports_dir):
            p.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
