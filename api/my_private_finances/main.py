from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from my_private_finances.api.router import api_router
from my_private_finances.config import get_data_dir
from my_private_finances.db import (
    DEFAULT_DB_PATH,
    create_engine,
    create_session_factory,
)
from my_private_finances.logging_config import setup_logging
from my_private_finances.models.watch_folder_config import WatchSettings
from my_private_finances.services.watch_folder import watch_folder_task

setup_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    session_factory: async_sessionmaker[AsyncSession] = app.state.session_factory

    # Resolve watch root from DB (or use default)
    root_path: Path
    default_watch = get_data_dir() / "watch"
    try:
        async with session_factory() as session:
            settings = await session.get(WatchSettings, 1)
            root_path = Path(settings.root_path) if settings else default_watch
    except Exception:
        root_path = default_watch
        logger.warning(
            "Could not read watch settings from DB, using default", exc_info=True
        )

    task = asyncio.create_task(watch_folder_task(session_factory, root_path))
    app.state.watcher_task = task
    logger.info("Watch folder task started")

    yield

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    logger.info("Watch folder task stopped")


def create_app(db_path: Path = DEFAULT_DB_PATH) -> FastAPI:
    logger.info("Starting My Private Finances, database: %s", db_path)

    app = FastAPI(title="My Private Finances", lifespan=_lifespan)

    engine: AsyncEngine = create_engine()
    session_factory: async_sessionmaker[AsyncSession] = create_session_factory(engine)

    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.db_path = db_path
    app.include_router(api_router, prefix="/api")

    return app


app = create_app()
