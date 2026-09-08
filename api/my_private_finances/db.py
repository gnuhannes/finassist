from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import event
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


def _enable_sqlite_foreign_keys(engine: AsyncEngine) -> None:
    """SQLite does not enforce foreign keys unless `PRAGMA foreign_keys=ON` is
    issued per connection. Attach it to the underlying sync engine's connect
    event so every pooled connection (including aiosqlite's) has it set."""

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragma(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_engine(database_url: str | None = None) -> AsyncEngine:
    url = database_url or get_database_url()
    ensure_sqlite_dir(url)
    engine = create_async_engine(url, echo=False, future=True)
    if url.startswith("sqlite"):
        _enable_sqlite_foreign_keys(engine)
    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        yield session
