"""CSV import bounds — upload size and row count (issue #98)."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient

from my_private_finances.services.csv_import import import_transactions_from_csv_path
from tests.helpers import create_account


@pytest.mark.asyncio
async def test_oversize_csv_upload_is_rejected(test_app: AsyncClient) -> None:
    acc = await create_account(test_app)
    oversize = b"booking_date,amount,currency,payee,purpose\n" + b"x" * (
        21 * 1024 * 1024
    )

    res = await test_app.post(
        f"/api/imports/csv?account_id={acc['id']}",
        files={"file": ("big.csv", oversize, "text/csv")},
    )
    assert res.status_code == 413


@pytest.mark.asyncio
async def test_row_count_over_limit_raises_before_any_write(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    acc = await create_account(test_app)
    csv_file = tmp_path / "many.csv"
    rows = "\n".join(
        f"2026-01-{d:02d},-1.00,EUR,Shop{d},x,ext-{d}" for d in range(1, 6)
    )
    csv_file.write_text(
        "booking_date,amount,currency,payee,purpose,external_id\n" + rows + "\n",
        encoding="utf-8",
    )

    session_factory = test_app._transport.app.state.session_factory  # type: ignore[attr-defined]
    async with session_factory() as session:
        with pytest.raises(ValueError, match="row"):
            await import_transactions_from_csv_path(
                session=session,
                account_id=acc["id"],
                csv_path=csv_file,
                max_rows=2,
            )

    # Nothing was written.
    listing = await test_app.get(f"/api/transactions?account_id={acc['id']}")
    assert listing.json()["total"] == 0
