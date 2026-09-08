"""Money precision in reporting (issue #111 / finding C3)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient

from my_private_finances.utils.money import money_from_db
from tests.helpers import create_account, create_transaction


def test_money_from_db_absorbs_float_noise() -> None:
    assert money_from_db(0.1 + 0.2) == Decimal("0.30")
    assert money_from_db(None) == Decimal("0.00")
    assert money_from_db(Decimal("12.34")) == Decimal("12.34")


@pytest.mark.asyncio
async def test_monthly_report_sum_is_exact_to_the_cent(test_app: AsyncClient) -> None:
    acc = await create_account(test_app)
    for i, amount in enumerate(["-0.10", "-0.20", "-0.10"]):
        await create_transaction(
            test_app,
            account_id=acc["id"],
            booking_date="2026-03-05",
            amount=amount,
            external_id=f"m{i}",
        )

    body = (
        await test_app.get(
            "/api/reports/monthly",
            params={"month": "2026-03", "account_id": acc["id"]},
        )
    ).json()
    assert body["expense_total"] == "-0.40"
    assert body["net_total"] == "-0.40"
