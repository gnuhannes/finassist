from pathlib import Path

import pytest

from my_private_finances.config import Settings


@pytest.fixture(autouse=True)
def _clear_config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start each test from a clean environment (CI sets DATABASE_URL)."""
    monkeypatch.delenv("DATA_DIR", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)


def test_defaults_hang_off_data_dir() -> None:
    settings = Settings(data_dir=Path("/srv/mpf"))

    assert settings.sqlite_path == Path("/srv/mpf/my_private_finances.sqlite")
    assert settings.ml_model_path == Path("/srv/mpf/ml_model.joblib")
    assert settings.watch_root == Path("/srv/mpf/watch")
    assert settings.resolved_database_url == (
        "sqlite+aiosqlite:////srv/mpf/my_private_finances.sqlite"
    )


def test_database_url_overrides_only_the_database() -> None:
    settings = Settings(
        data_dir=Path("/srv/mpf"),
        database_url="postgresql+asyncpg://user@host/db",
    )

    assert settings.resolved_database_url == "postgresql+asyncpg://user@host/db"
    # Everything else still lives under data_dir.
    assert settings.ml_model_path == Path("/srv/mpf/ml_model.joblib")
    assert settings.watch_root == Path("/srv/mpf/watch")


def test_reads_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DIR", "/from/env")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///custom.sqlite")

    settings = Settings()

    assert settings.data_dir == Path("/from/env")
    assert settings.resolved_database_url == "sqlite+aiosqlite:///custom.sqlite"
