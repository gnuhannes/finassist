"""SQLite foreign-key enforcement (issue #96).

`PRAGMA foreign_keys=ON` is attached per connection in `db.create_engine`, so
referential integrity is enforced at runtime and the API turns the resulting
`IntegrityError` into a 409/422 instead of a silent orphan row or a 500.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import create_account, create_budget, create_category


@pytest.mark.asyncio
async def test_pragma_foreign_keys_is_enabled(db_session: AsyncSession) -> None:
    result = await db_session.execute(text("PRAGMA foreign_keys"))
    assert result.scalar_one() == 1


@pytest.mark.asyncio
async def test_create_transaction_with_unknown_category_returns_422(
    test_app: AsyncClient,
) -> None:
    account = await create_account(test_app)
    res = await test_app.post(
        "/api/transactions",
        json={
            "account_id": account["id"],
            "booking_date": "2026-02-01",
            "amount": "10.00",
            "currency": "EUR",
            "payee": "X",
            "purpose": "Y",
            "import_source": "manual",
            "external_id": "fk-1",
            "category_id": 999999,
        },
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_delete_category_referenced_by_budget_returns_409(
    test_app: AsyncClient,
) -> None:
    cat = await create_category(test_app, name="Rent")
    await create_budget(test_app, category_id=cat["id"], amount="900.00")

    res = await test_app.delete(f"/api/categories/{cat['id']}")
    assert res.status_code == 409

    # The category and its budget are both still there.
    assert len((await test_app.get("/api/categories")).json()) == 1


@pytest.mark.asyncio
async def test_delete_csv_profile_in_use_returns_409(test_app: AsyncClient) -> None:
    account = await create_account(test_app)
    profile = (await test_app.post("/api/csv-profiles", json={"name": "Bank X"})).json()
    cfg = await test_app.post(
        "/api/watch-folder/configs",
        json={
            "subfolder_name": "bank-x",
            "account_id": account["id"],
            "profile_id": profile["id"],
        },
    )
    assert cfg.status_code == 201, cfg.text

    res = await test_app.delete(f"/api/csv-profiles/{profile['id']}")
    assert res.status_code == 409
