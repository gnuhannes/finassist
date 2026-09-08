from __future__ import annotations

import logging
import os
import re
import sqlite3
import tempfile
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, func, select

from my_private_finances.db import sqlite_path_from_engine
from my_private_finances.deps import SessionDep
from my_private_finances.models import (
    Account,
    Budget,
    CategorizationRule,
    Category,
    CsvProfile,
    RecurringPattern,
    Transaction,
    TransferCandidate,
)

router = APIRouter(tags=["data"])

logger = logging.getLogger(__name__)

_SQLITE_MAGIC = b"SQLite format 3\x00"
_MAX_RESTORE_BYTES = 500 * 1024 * 1024  # 500 MB
_VERSIONS_DIR = Path(__file__).resolve().parents[3] / "alembic" / "versions"


@lru_cache(maxsize=1)
def _known_alembic_revisions() -> frozenset[str]:
    """Revision ids of migrations shipped with this build."""
    revisions: set[str] = set()
    for path in _VERSIONS_DIR.glob("*.py"):
        match = re.search(
            r"""^revision(?::\s*str)?\s*=\s*["']([^"']+)["']""",
            path.read_text(),
            re.MULTILINE,
        )
        if match:
            revisions.add(match.group(1))
    return frozenset(revisions)


_CORE_TABLES = {"account", "transaction", "category"}


def _validate_restore_candidate(path: str) -> None:
    """Raise HTTPException unless *path* is an intact My Private Finances DB."""
    conn = sqlite3.connect(path)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise HTTPException(status_code=400, detail="SQLite integrity check failed")

        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if not _CORE_TABLES <= tables:
            raise HTTPException(
                status_code=400, detail="Not a recognised My Private Finances backup"
            )

        if "alembic_version" in tables:
            row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
            known = _known_alembic_revisions()
            if row is not None and known and row[0] not in known:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Backup schema revision is not recognised by this "
                        "version — restore it into a matching build, then upgrade."
                    ),
                )
    except sqlite3.DatabaseError as e:
        raise HTTPException(
            status_code=400, detail="Not a recognised My Private Finances backup"
        ) from e
    finally:
        conn.close()


def _sqlite_copy(src_path: str, dst_path: str) -> None:
    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(dst_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


@router.post("/restore/sqlite", status_code=200)
async def restore_sqlite(file: UploadFile, request: Request) -> dict:
    data = await file.read()
    if len(data) > _MAX_RESTORE_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 500 MB)")
    if data[:16] != _SQLITE_MAGIC:
        raise HTTPException(status_code=400, detail="Not a valid SQLite file")

    lock = request.app.state.restore_lock
    if lock.locked():
        raise HTTPException(status_code=409, detail="A restore is already in progress")

    tmp_path: str | None = None
    async with lock:
        try:
            with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
                tmp.write(data)
                tmp_path = tmp.name

            _validate_restore_candidate(tmp_path)

            dst_path = str(sqlite_path_from_engine(request.app.state.engine))
            # Release all pooled async connections before writing
            await request.app.state.engine.dispose()

            await run_in_threadpool(_sqlite_copy, tmp_path, dst_path)
        finally:
            if tmp_path is not None:
                os.unlink(tmp_path)

    logger.info("Database restored from uploaded SQLite backup")
    return {"ok": True}


async def _count(session: SessionDep, model: type) -> int:
    result = await session.execute(select(func.count()).select_from(model))  # type: ignore[arg-type]
    return int(result.scalar_one())


@router.delete("/data/transactions", status_code=200)
async def delete_transactions(session: SessionDep) -> dict:
    """Delete all transactions, transfer candidates, and recurring patterns."""
    models = [TransferCandidate, RecurringPattern, Transaction]
    deleted = sum([await _count(session, m) for m in models])
    for model in models:
        await session.execute(delete(model))
    await session.commit()
    logger.info("Deleted all transactions: %d rows total", deleted)
    return {"deleted": deleted}


@router.delete("/data", status_code=200)
async def wipe_all_data(session: SessionDep) -> dict:
    """Delete all data from all tables in FK-safe order."""
    models = [
        TransferCandidate,
        RecurringPattern,
        Transaction,
        Budget,
        CategorizationRule,
        CsvProfile,
        Category,
        Account,
    ]
    deleted = sum([await _count(session, m) for m in models])
    for model in models:
        await session.execute(delete(model))
    await session.commit()
    logger.info("Wiped all data: %d rows deleted", deleted)
    return {"deleted": deleted}
