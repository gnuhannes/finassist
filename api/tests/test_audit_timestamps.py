"""created_at / updated_at audit columns (issue #110 / C15)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from my_private_finances.models import Account
from tests.helpers import create_account, create_transaction


@pytest.mark.asyncio
async def test_timestamps_set_on_insert_and_bump_on_update(
    db_session: AsyncSession,
) -> None:
    acc = Account(name="Main", currency="EUR")
    db_session.add(acc)
    await db_session.commit()
    await db_session.refresh(acc)

    assert acc.created_at is not None
    assert acc.updated_at is not None
    first_updated = acc.updated_at

    acc.name = "Renamed"
    await db_session.commit()
    await db_session.refresh(acc)

    assert acc.updated_at >= first_updated
    assert acc.created_at <= acc.updated_at


@pytest.mark.asyncio
async def test_transaction_read_exposes_created_at(test_app: AsyncClient) -> None:
    acc = await create_account(test_app)
    tx = await create_transaction(test_app, account_id=acc["id"], external_id="ts-1")
    assert tx["created_at"] is not None

    listed = await test_app.get("/api/transactions", params={"account_id": acc["id"]})
    assert listed.json()["items"][0]["created_at"] is not None
