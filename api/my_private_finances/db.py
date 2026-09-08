from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

DEFAULT_DB_PATH = Path("data") / "my_private_finances.sqlite"


def build_sqlite_url(db_path: Path) -> str:
    return f"sqlite+aiosqlite:///{db_path.as_posix()}"


def get_database_url() -> str:
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return env_url
    return build_sqlite_url(DEFAULT_DB_PATH)


def ensure_sqlite_dir(database_url: str) -> None:
    # Only handle local sqlite file URLs; for anything else, do nothing.
    prefix = "sqlite+aiosqlite:///"
    if database_url.startswith(prefix):
        path_str = database_url[len(prefix) :]
        db_path = Path(path_str)
        db_path.parent.mkdir(parents=True, exist_ok=True)


def create_engine(database_url: str | None = None) -> AsyncEngine:
    url = database_url or get_database_url()
    ensure_sqlite_dir(url)
    return create_async_engine(url, echo=False, future=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def sqlite_path_from_engine(engine: AsyncEngine) -> Path:
    """The on-disk SQLite file backing *engine*.

    Use this instead of a separately-tracked path: export/restore must operate
    on the file the engine is actually connected to, which is derived from
    ``DATABASE_URL`` and may differ from ``DEFAULT_DB_PATH``.
    """
    url = engine.url
    if not url.drivername.startswith("sqlite"):
        raise ValueError(f"Not a SQLite engine: {url.drivername}")
    if not url.database or url.database == ":memory:":
        raise ValueError("SQLite engine is not backed by a file")
    return Path(url.database)


async def get_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        yield session
