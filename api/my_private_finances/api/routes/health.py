from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from my_private_finances.services.watch_folder import WatcherStatus

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    status: WatcherStatus | None = getattr(request.app.state, "watcher_status", None)
    watcher: dict[str, Any] | None = None
    if status is not None:
        watcher = {
            "running": status.running,
            "last_error": status.last_error,
            "restarts": status.restarts,
            "files_processed": status.files_processed,
            "root_path": status.root_path,
        }
    return {"status": "ok", "watcher": watcher}
