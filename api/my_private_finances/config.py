from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Single source of runtime configuration.

    Everything on-disk hangs off ``data_dir`` (env ``DATA_DIR``). ``DATABASE_URL``
    is an optional override for the database only; when unset the database lives
    inside ``data_dir``. Nothing else in the codebase should read the environment
    for these values.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    database_url: str | None = None
    log_level: str = "INFO"

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "my_private_finances.sqlite"

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite+aiosqlite:///{self.sqlite_path.as_posix()}"

    @property
    def ml_model_path(self) -> Path:
        return self.data_dir / "ml_model.joblib"

    @property
    def watch_root(self) -> Path:
        return self.data_dir / "watch"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings, read from the environment once."""
    return Settings()
