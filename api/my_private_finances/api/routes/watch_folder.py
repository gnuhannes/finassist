from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlmodel import delete

from my_private_finances.config import get_data_dir
from my_private_finances.deps import SessionDep
from my_private_finances.models.watch_folder_config import (
    WatchFolderConfig,
    WatchSettings,
)
from my_private_finances.schemas.watch_folder import (
    WatchFolderConfigCreate,
    WatchFolderConfigRead,
    WatchFolderConfigUpdate,
    WatchSettingsRead,
    WatchSettingsUpdate,
)
from my_private_finances.services.watch_folder import watch_folder_task

router = APIRouter(prefix="/watch-folder", tags=["watch-folder"])

logger = logging.getLogger(__name__)

_SETTINGS_ID = 1


async def _get_or_create_settings(session: SessionDep) -> WatchSettings:
    settings = await session.get(WatchSettings, _SETTINGS_ID)
    if settings is None:
        settings = WatchSettings(
            id=_SETTINGS_ID, root_path=str(get_data_dir() / "watch")
        )
        session.add(settings)
        await session.commit()
        await session.refresh(settings)
    return settings


@router.get("/settings", response_model=WatchSettingsRead)
async def get_watch_settings(session: SessionDep) -> WatchSettings:
    return await _get_or_create_settings(session)


@router.patch("/settings", response_model=WatchSettingsRead)
async def update_watch_settings(
    body: WatchSettingsUpdate,
    request: Request,
    session: SessionDep,
) -> WatchSettings:
    settings = await _get_or_create_settings(session)
    settings.root_path = body.root_path
    session.add(settings)
    await session.commit()
    await session.refresh(settings)

    # Restart the background watcher with the new path
    old_task: asyncio.Task[None] | None = getattr(
        request.app.state, "watcher_task", None
    )
    if old_task is not None and not old_task.done():
        old_task.cancel()
        try:
            await old_task
        except asyncio.CancelledError:
            pass

    new_task = asyncio.create_task(
        watch_folder_task(
            request.app.state.session_factory,
            Path(settings.root_path),
        )
    )
    request.app.state.watcher_task = new_task
    logger.info("Watch folder restarted at: %s", settings.root_path)

    return settings


@router.get("/configs", response_model=list[WatchFolderConfigRead])
async def list_watch_configs(session: SessionDep) -> list[WatchFolderConfig]:
    result = await session.execute(select(WatchFolderConfig))
    return list(result.scalars().all())


@router.post("/configs", response_model=WatchFolderConfigRead, status_code=201)
async def create_watch_config(
    body: WatchFolderConfigCreate,
    session: SessionDep,
) -> WatchFolderConfig:
    config = WatchFolderConfig(**body.model_dump())
    session.add(config)
    try:
        await session.commit()
    except Exception as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Subfolder '{body.subfolder_name}' is already configured",
        ) from exc
    await session.refresh(config)
    return config


@router.put("/configs/{config_id}", response_model=WatchFolderConfigRead)
async def update_watch_config(
    config_id: int,
    body: WatchFolderConfigUpdate,
    session: SessionDep,
) -> WatchFolderConfig:
    config = await session.get(WatchFolderConfig, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Watch folder config not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(config, field, value)
    session.add(config)
    await session.commit()
    await session.refresh(config)
    return config


@router.delete("/configs/{config_id}", status_code=204)
async def delete_watch_config(config_id: int, session: SessionDep) -> None:
    config = await session.get(WatchFolderConfig, config_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Watch folder config not found")
    await session.execute(
        delete(WatchFolderConfig).where(WatchFolderConfig.id == config_id)  # type: ignore[arg-type]
    )
    await session.commit()
