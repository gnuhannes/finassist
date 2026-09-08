import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlmodel import SQLModel

from my_private_finances.config import Settings
from my_private_finances.db import create_engine, create_session_factory
from my_private_finances.main import create_app


def _test_settings(tmpdir: str) -> Settings:
    # Pin both data_dir and database_url so an ambient DATABASE_URL in the
    # environment (CI sets one) can't leak a shared DB into the tests. The URL
    # points at the same file Settings.sqlite_path derives, so app.state.db_path
    # and the engine agree (see export/restore).
    tmp = Path(tmpdir)
    db_file = tmp / "my_private_finances.sqlite"
    return Settings(
        data_dir=tmp,
        database_url=f"sqlite+aiosqlite:///{db_file.as_posix()}",
    )


@pytest_asyncio.fixture
async def test_app() -> AsyncGenerator[AsyncClient, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        app = create_app(_test_settings(tmpdir))
        engine: AsyncEngine = app.state.engine

        async with engine.connect() as conn:
            async with conn.begin():
                await conn.run_sync(SQLModel.metadata.create_all)

        transport = ASGITransport(app=app)
        # The SPA's fetch wrapper always sends X-Requested-With; mirror that so
        # the destructive-endpoint guard (#99) is transparent to normal tests.
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"X-Requested-With": "XMLHttpRequest"},
        ) as client:
            yield client

        await engine.dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        engine: AsyncEngine = create_engine(
            _test_settings(tmpdir).resolved_database_url
        )
        session_factory = create_session_factory(engine)

        async with engine.connect() as conn:
            async with conn.begin():
                await conn.run_sync(SQLModel.metadata.create_all)

        async with session_factory() as session:
            yield session

        await engine.dispose()
