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

    app_name: str = "UFABC Class Ranking"
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://ufabc:ufabc@localhost:5432/ufabc_ranking"
    import_storage_path: Path = Path("var/imports")
    log_level: str = Field(default="INFO", pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    ufabc_next_enabled: bool = True
    ufabc_next_base_url: str = "https://api.v2.ufabcnext.com"
    ufabc_next_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    ufabc_next_max_retries: int = Field(default=2, ge=0, le=5)
    ufabc_next_backoff_seconds: float = Field(default=0.5, ge=0, le=30)
    ufabc_next_min_interval_seconds: float = Field(default=0.1, ge=0, le=10)
    ufabc_next_component_cache_seconds: int = Field(default=900, ge=0)
    ufabc_next_review_cache_seconds: int = Field(default=86400, ge=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
