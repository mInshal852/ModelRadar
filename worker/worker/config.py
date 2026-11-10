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


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
