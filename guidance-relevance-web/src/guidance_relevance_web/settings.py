"""Environment-backed settings for the operator UI."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    grf_corpus: Path = Path("data/corpus")
    grf_jobs: Path = Path("data/jobs")
    grf_host: str = "127.0.0.1"
    grf_port: int = 8000
    grf_max_routed: int = 650
    grf_daily_max_routed: int = 2000
    grf_public_base_url: str = "http://127.0.0.1:8000"
    grf_enable_worker: bool = True
    grf_sweep_seconds: int = 120
    grf_queue_poll_seconds: float = 1.0
    grf_llm_mode: Literal["batch", "sync"] = "batch"
    grf_sync_concurrency: int = 10
    mail_from: str = "noreply@localhost"
    mail_url: str | None = None
    anthropic_api_key: str | None = None


def get_settings() -> Settings:
    return Settings()
