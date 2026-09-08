from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from sqlmodel import select
from starlette.background import BackgroundTask

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

router = APIRouter(prefix="/export", tags=["export"])

logger = logging.getLogger(__name__)


def _serialize(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Cannot JSON-serialize {type(obj)!r}")


def _sqlite_backup(src_path: str, dst_path: str) -> None:
    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(dst_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


@router.get("/sqlite")
async def export_sqlite(request: Request) -> FileResponse:
    db_path = sqlite_path_from_engine(request.app.state.engine)
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp.close()

    await run_in_threadpool(_sqlite_backup, str(db_path), tmp.name)

    filename = f"my_private_finances_{date.today()}.sqlite"
    logger.info("SQLite export prepared: %s", tmp.name)
    return FileResponse(
        tmp.name,
        filename=filename,
        media_type="application/octet-stream",
        background=BackgroundTask(os.unlink, tmp.name),
    )


@router.get("/json")
async def export_json(session: SessionDep) -> Response:
    # Query in FK-safe order (parents before children)
    categories = (await session.execute(select(Category))).scalars().all()
    accounts = (await session.execute(select(Account))).scalars().all()
    csv_profiles = (await session.execute(select(CsvProfile))).scalars().all()
    budgets = (await session.execute(select(Budget))).scalars().all()
    rules = (await session.execute(select(CategorizationRule))).scalars().all()
    transactions = (await session.execute(select(Transaction))).scalars().all()
    patterns = (await session.execute(select(RecurringPattern))).scalars().all()
    transfers = (await session.execute(select(TransferCandidate))).scalars().all()

    payload: dict[str, Any] = {
        "export_version": 1,
        "exported_at": datetime.now(UTC).isoformat(),
        "accounts": [m.model_dump() for m in accounts],
        "categories": [m.model_dump() for m in categories],
        "csv_profiles": [m.model_dump() for m in csv_profiles],
        "budgets": [m.model_dump() for m in budgets],
        "categorization_rules": [m.model_dump() for m in rules],
        "transactions": [m.model_dump() for m in transactions],
        "recurring_patterns": [m.model_dump() for m in patterns],
        "transfer_candidates": [m.model_dump() for m in transfers],
    }

    content = json.dumps(payload, default=_serialize, indent=2)
    filename = f"my_private_finances_{date.today()}.json"
    logger.info(
        "JSON export prepared: %d accounts, %d transactions",
        len(accounts),
        len(transactions),
    )
    return Response(
        content=content.encode(),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
