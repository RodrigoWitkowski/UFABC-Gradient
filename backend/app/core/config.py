from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Gradient"
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://ufabc:ufabc@localhost:5433/ufabc_ranking"
    import_storage_path: Path = Path("var/imports")
    log_level: str = Field(default="INFO", pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    api_docs_enabled: bool = False
    ufabc_next_enabled: bool = True
    ufabc_next_base_url: str = "https://api.v2.ufabcnext.com"
    ufabc_next_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    ufabc_next_max_retries: int = Field(default=0, ge=0, le=2)
    ufabc_next_backoff_seconds: float = Field(default=5.0, ge=0, le=60)
    ufabc_next_min_interval_seconds: float = Field(default=5.0, ge=0, le=60)
    ufabc_next_max_requests_per_sync: int = Field(default=30, ge=1, le=100)
    ufabc_next_component_cache_seconds: int = Field(default=86400, ge=0)
    ufabc_next_review_cache_seconds: int = Field(default=7776000, ge=0)
    ufabc_next_sync_stale_seconds: int = Field(default=3600, ge=300, le=86400)


@lru_cache
def get_settings() -> Settings:
    return Settings()
