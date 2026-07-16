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


@lru_cache
def get_settings() -> Settings:
    return Settings()
