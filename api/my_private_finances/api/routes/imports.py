from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, UploadFile
from my_private_finances.deps import SessionDep
from my_private_finances.models import CsvProfile
from my_private_finances.schemas import ImportResultResponse
from my_private_finances.services.csv_import import (
    ColumnMap,
    import_transactions_from_csv_path,
)
from my_private_finances.services.recurring_detection import run_detection

router = APIRouter(prefix="/imports", tags=["imports"])

logger = logging.getLogger(__name__)

_MAX_CSV_BYTES = 20 * 1024 * 1024  # 20 MB
_READ_CHUNK = 1 * 1024 * 1024


def _too_large() -> HTTPException:
    limit_mb = _MAX_CSV_BYTES // (1024 * 1024)
    return HTTPException(
        status_code=413, detail=f"CSV file too large (max {limit_mb} MB)"
    )


async def _spool_upload_to_tmp(file: UploadFile) -> tuple[Path, int]:
    """Stream the upload to a temp file, enforcing the size cap without ever
    holding the whole file in memory."""
    if file.size is not None and file.size > _MAX_CSV_BYTES:
        raise _too_large()

    total = 0
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        while chunk := await file.read(_READ_CHUNK):
            total += len(chunk)
            if total > _MAX_CSV_BYTES:
                tmp_path.unlink(missing_ok=True)
                raise _too_large()
            tmp.write(chunk)
    return tmp_path, total


@router.post("/csv", response_model=ImportResultResponse)
async def import_csv(
    file: UploadFile,
    session: SessionDep,
    account_id: Annotated[int, Query()],
    delimiter: Annotated[str | None, Query()] = None,
    date_format: Annotated[str | None, Query()] = None,
    decimal_comma: Annotated[bool | None, Query()] = None,
    profile_id: Annotated[int | None, Query()] = None,
) -> ImportResultResponse:
    tmp_path, size = await _spool_upload_to_tmp(file)
    try:
        return await _run_import(
            file,
            tmp_path,
            size,
            session,
            account_id,
            delimiter,
            date_format,
            decimal_comma,
            profile_id,
        )
    finally:
        tmp_path.unlink(missing_ok=True)


async def _run_import(
    file: UploadFile,
    tmp_path: Path,
    size: int,
    session: SessionDep,
    account_id: int,
    delimiter: str | None,
    date_format: str | None,
    decimal_comma: bool | None,
    profile_id: int | None,
) -> ImportResultResponse:
    logger.info(
        "CSV import request: account_id=%d, filename=%r, size=%d bytes, profile_id=%s",
        account_id,
        file.filename,
        size,
        profile_id,
    )

    # Resolve effective settings: explicit param → profile default → service default
    column_map: ColumnMap | None = None
    profile_delimiter: str = ","
    profile_date_format: str = "iso"
    profile_decimal_comma: bool = False
    row_filters: dict | None = None
    row_exclude_filters: dict | None = None

    if profile_id is not None:
        profile = await session.get(CsvProfile, profile_id)
        if profile is None:
            raise HTTPException(
                status_code=404, detail=f"CSV profile {profile_id} not found"
            )
        profile_delimiter = profile.delimiter
        profile_date_format = profile.date_format
        profile_decimal_comma = profile.decimal_comma
        if profile.column_map:
            column_map = profile.column_map  # type: ignore[assignment]
        row_filters = profile.row_filters
        row_exclude_filters = profile.row_exclude_filters

    effective_delimiter = delimiter if delimiter is not None else profile_delimiter
    effective_date_format = (
        date_format if date_format is not None else profile_date_format
    )
    effective_decimal_comma = (
        decimal_comma if decimal_comma is not None else profile_decimal_comma
    )

    try:
        result = await import_transactions_from_csv_path(
            session=session,
            account_id=account_id,
            csv_path=tmp_path,
            delimiter=effective_delimiter,
            date_format=effective_date_format,
            decimal_comma=effective_decimal_comma,
            column_map=column_map,
            row_filters=row_filters,
            row_exclude_filters=row_exclude_filters,
        )
    except ValueError as e:
        msg = str(e)
        logger.warning("CSV import rejected: account_id=%d, reason=%s", account_id, msg)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg) from e
        raise HTTPException(status_code=400, detail=msg) from e

    if result.created > 0:
        try:
            await run_detection(session, account_id)
        except Exception:
            logger.warning(
                "Auto recurring-detection failed after CSV import for account_id=%d",
                account_id,
                exc_info=True,
            )

    return ImportResultResponse(
        total_rows=result.total_rows,
        created=result.created,
        skipped=result.skipped,
        duplicates=result.duplicates,
        failed=result.failed,
        errors=result.errors,
        errors_truncated=result.errors_truncated,
    )
