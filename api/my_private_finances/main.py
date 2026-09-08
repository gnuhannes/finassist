from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from my_private_finances.api.router import api_router
from my_private_finances.config import Settings, get_settings
from my_private_finances.db import create_engine, create_session_factory
from my_private_finances.logging_config import setup_logging
from my_private_finances.models.watch_folder_config import WatchSettings
from my_private_finances.services.exceptions import ServiceError
from my_private_finances.services.watch_folder import watch_folder_task

setup_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    session_factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    settings: Settings = app.state.settings

    # Resolve watch root from DB (or use the configured default)
    root_path: Path
    default_watch = settings.watch_root
    try:
        async with session_factory() as session:
            watch_config = await session.get(WatchSettings, 1)
            root_path = Path(watch_config.root_path) if watch_config else default_watch
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


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logger.info(
        "Starting My Private Finances (data_dir=%s, database=%s)",
        settings.data_dir,
        settings.resolved_database_url,
    )

    app = FastAPI(title="My Private Finances", lifespan=_lifespan)

    @app.exception_handler(ServiceError)
    async def _service_error_handler(
        request: Request, exc: ServiceError
    ) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    engine: AsyncEngine = create_engine(settings.resolved_database_url)
    session_factory: async_sessionmaker[AsyncSession] = create_session_factory(engine)

    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.db_path = settings.sqlite_path
    app.state.restore_lock = asyncio.Lock()
    app.include_router(api_router, prefix="/api")

    return app


app = create_app()
