from __future__ import annotations

import asyncio
import logging
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from watchdog.events import (  # type: ignore[import-untyped]
    FileCreatedEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer  # type: ignore[import-untyped]

from my_private_finances.models import CsvProfile
from my_private_finances.models.watch_folder_config import WatchFolderConfig
from my_private_finances.services.csv_import import import_transactions_from_csv_path
from my_private_finances.services.recurring_detection import run_detection

logger = logging.getLogger(__name__)


class _QueueHandler(FileSystemEventHandler):
    """Watchdog event handler that forwards file-creation events to an asyncio queue."""

    def __init__(
        self, queue: asyncio.Queue[Path], loop: asyncio.AbstractEventLoop
    ) -> None:
        super().__init__()
        self._queue = queue
        self._loop = loop

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        path = Path(str(event.src_path))
        if path.suffix.lower() == ".csv":
            asyncio.run_coroutine_threadsafe(self._queue.put(path), self._loop)


async def _process_file(
    path: Path,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Import a single watched file into the database."""
    subfolder_name = path.parent.name
    watch_root = path.parent.parent  # e.g. data/watch
    data_root = watch_root.parent
    processed_dir = data_root / "processed" / date.today().isoformat()
    failed_dir = data_root / "failed"

    # Guard against path traversal: resolved path must stay within data_root
    try:
        path.resolve().relative_to(data_root.resolve())
    except ValueError:
        logger.error("Rejected file outside watch root: %s", path)
        return

    async with session_factory() as session:
        db_result = await session.execute(
            select(WatchFolderConfig).where(
                WatchFolderConfig.subfolder_name == subfolder_name  # type: ignore[arg-type]
            )
        )
        config = db_result.scalars().first()

        if config is None:
            msg = f"No watch folder config for subfolder '{subfolder_name}'"
            logger.warning(msg)
            _move_to_failed(path, failed_dir, msg)
            return

        try:
            profile = None
            if config.profile_id is not None:
                profile = await session.get(CsvProfile, config.profile_id)

            kwargs: dict[str, object] = {}
            if profile is not None:
                kwargs["delimiter"] = profile.delimiter
                kwargs["date_format"] = profile.date_format
                kwargs["decimal_comma"] = profile.decimal_comma
                if profile.column_map:
                    kwargs["column_map"] = profile.column_map

            import_result = await import_transactions_from_csv_path(
                session=session,
                account_id=config.account_id,
                csv_path=path,
                **kwargs,  # type: ignore[arg-type]
            )

            if import_result.created > 0:
                try:
                    await run_detection(session, config.account_id)
                except Exception:
                    logger.warning(
                        "Auto recurring-detection failed for watch import",
                        exc_info=True,
                    )

            _move_to_processed(path, processed_dir)
            logger.info(
                "Watch import: %s → created=%d duplicates=%d failed=%d",
                path.name,
                import_result.created,
                import_result.duplicates,
                import_result.failed,
            )
        except Exception as exc:
            logger.error(
                "Watch import failed for %s: %s", path.name, exc, exc_info=True
            )
            _move_to_failed(path, failed_dir, str(exc))


def _move_to_processed(path: Path, processed_dir: Path) -> None:
    processed_dir.mkdir(parents=True, exist_ok=True)
    dest = processed_dir / path.name
    counter = 1
    while dest.exists():
        dest = processed_dir / f"{path.stem}_{counter}{path.suffix}"
        counter += 1
    path.rename(dest)


def _move_to_failed(path: Path, failed_dir: Path, error: str) -> None:
    failed_dir.mkdir(parents=True, exist_ok=True)
    dest = failed_dir / path.name
    counter = 1
    while dest.exists():
        dest = failed_dir / f"{path.stem}_{counter}{path.suffix}"
        counter += 1
    try:
        path.rename(dest)
        dest.with_suffix(dest.suffix + ".error.txt").write_text(error, encoding="utf-8")
    except Exception:
        logger.warning("Failed to move %s to failed dir", path.name, exc_info=True)


async def watch_folder_task(
    session_factory: async_sessionmaker[AsyncSession],
    watch_path: Path,
) -> None:
    """Long-running asyncio task that watches *watch_path* and auto-imports files."""
    watch_path.mkdir(parents=True, exist_ok=True)
    queue: asyncio.Queue[Path] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    handler = _QueueHandler(queue, loop)
    observer = Observer()
    observer.schedule(handler, str(watch_path), recursive=True)
    observer.start()
    logger.info("Watch folder started: %s", watch_path)

    try:
        while True:
            path = await queue.get()
            await asyncio.sleep(0.5)  # debounce — wait for file write to finish
            if not path.exists():
                continue
            await _process_file(path, session_factory)
    except asyncio.CancelledError:
        logger.info("Watch folder task cancelled, stopping observer")
        observer.stop()
        observer.join()
        raise
