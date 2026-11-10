from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings, read from environment variables only."""

    model_config = SettingsConfigDict(extra="ignore")

    database_url: str
    environment: str = "development"
    config_dir: Path = Path("/config")
    heartbeat_file: Path = Path("/tmp/worker-heartbeat")  # noqa: S108
    heartbeat_interval_seconds: int = 30

    # RSS/Atom ingestion (Phase 2)
    ingestion_enabled: bool = True
    ingestion_tick_seconds: int = 60
    http_timeout_seconds: float = 20.0
    http_max_attempts: int = 3
    http_backoff_base_seconds: float = 2.0
    http_domain_min_interval_seconds: float = 2.0


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
