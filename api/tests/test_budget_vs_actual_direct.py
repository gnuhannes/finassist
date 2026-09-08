"""Direct-call tests for budget-vs-actual report (registers in pytest-cov)."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from my_private_finances.models import Account, Budget, Category, Transaction
from my_private_finances.services.reporting import (
    AccountNotFound,
    InvalidMonth,
    budget_vs_actual,
    parse_month,
)


def test_parse_month_valid() -> None:
    start, end = parse_month("2026-05")
    assert start == date(2026, 5, 1)
    assert end == date(2026, 6, 1)


def test_parse_month_december() -> None:
    start, end = parse_month("2026-12")
    assert start == date(2026, 12, 1)
    assert end == date(2027, 1, 1)


def test_parse_month_invalid_format() -> None:
    with pytest.raises(InvalidMonth):
        parse_month("bad")


def test_parse_month_invalid_month_number() -> None:
    with pytest.raises(InvalidMonth):
        parse_month("2026-13")


@pytest.mark.asyncio
async def test_budget_vs_actual_direct(db_session: AsyncSession) -> None:
    acc = Account(name="Main", currency="EUR")
    db_session.add(acc)
    await db_session.commit()
    await db_session.refresh(acc)

    cat = Category(name="Groceries")
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)

    db_session.add(Budget(category_id=cat.id, amount=Decimal("300.00")))  # type: ignore[arg-type]
    await db_session.commit()

    tx = Transaction(
        account_id=acc.id,  # type: ignore[arg-type]
        booking_date=date(2026, 5, 10),
        amount=Decimal("-120.00"),
        currency="EUR",
        payee="REWE",
        purpose="Food",
        import_source="manual",
        import_hash="hash1",
        category_id=cat.id,  # type: ignore[arg-type]
    )
    db_session.add(tx)
    await db_session.commit()

    result = await budget_vs_actual(
        db_session,
        month="2026-05",
        account_id=acc.id,
    )

    assert len(result) == 1
    assert result[0].category_name == "Groceries"
    assert result[0].budgeted == Decimal("300.00")
    assert result[0].actual == Decimal("120.00")
    assert result[0].remaining == Decimal("180.00")


@pytest.mark.asyncio
async def test_budget_vs_actual_account_not_found(db_session: AsyncSession) -> None:
    with pytest.raises(AccountNotFound):
        await budget_vs_actual(db_session, month="2026-05", account_id=99999)
