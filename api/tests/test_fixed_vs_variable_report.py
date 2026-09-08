"""Direct-call tests for fixed-vs-variable report."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from my_private_finances.models import Account, Category, Transaction
from my_private_finances.services.reporting import AccountNotFound, fixed_vs_variable


async def _seed(session: AsyncSession) -> tuple[Account, Category, Category, Category]:
    acc = Account(name="Main", currency="EUR")
    session.add(acc)
    await session.commit()
    await session.refresh(acc)

    cat_fixed = Category(name="Rent", cost_type="fixed")
    cat_variable = Category(name="Groceries", cost_type="variable")
    cat_none = Category(name="Other")
    session.add_all([cat_fixed, cat_variable, cat_none])
    await session.commit()
    for c in [cat_fixed, cat_variable, cat_none]:
        await session.refresh(c)

    return acc, cat_fixed, cat_variable, cat_none


def _tx(
    account_id: int,
    category_id: int | None,
    amount: str,
    day: int,
    hash_suffix: str,
) -> Transaction:
    return Transaction(
        account_id=account_id,
        booking_date=date(2026, 5, day),
        amount=Decimal(amount),
        currency="EUR",
        payee="Test",
        purpose="Test",
        import_source="manual",
        import_hash=f"fvv-{hash_suffix}",
        category_id=category_id,
    )


@pytest.mark.asyncio
async def test_fixed_vs_variable_basic(db_session: AsyncSession) -> None:
    acc, cat_fixed, cat_variable, cat_none = await _seed(db_session)

    db_session.add_all(
        [
            _tx(acc.id, cat_fixed.id, "-500.00", 1, "1"),  # type: ignore[arg-type]
            _tx(acc.id, cat_variable.id, "-120.00", 5, "2"),  # type: ignore[arg-type]
            _tx(acc.id, cat_variable.id, "-80.00", 10, "3"),  # type: ignore[arg-type]
            _tx(acc.id, cat_none.id, "-50.00", 15, "4"),  # type: ignore[arg-type]
        ]
    )
    await db_session.commit()

    result = await fixed_vs_variable(
        db_session,
        month="2026-05",
        account_id=acc.id,
    )

    assert result.account_id == acc.id
    assert result.currency == "EUR"
    assert result.fixed_total == Decimal("500.00")
    assert result.variable_total == Decimal("200.00")
    assert result.unclassified_total == Decimal("50.00")
    assert len(result.breakdown) == 3


@pytest.mark.asyncio
async def test_fixed_vs_variable_no_expenses(db_session: AsyncSession) -> None:
    acc, _, _, _ = await _seed(db_session)

    result = await fixed_vs_variable(
        db_session,
        month="2026-05",
        account_id=acc.id,
    )

    assert result.fixed_total == Decimal("0")
    assert result.variable_total == Decimal("0")
    assert result.unclassified_total == Decimal("0")
    assert result.breakdown == []


@pytest.mark.asyncio
async def test_fixed_vs_variable_ignores_income(db_session: AsyncSession) -> None:
    acc, cat_fixed, _, _ = await _seed(db_session)

    db_session.add_all(
        [
            _tx(acc.id, cat_fixed.id, "-500.00", 1, "5"),  # type: ignore[arg-type]
            _tx(acc.id, cat_fixed.id, "1000.00", 2, "6"),  # type: ignore[arg-type]
        ]
    )
    await db_session.commit()

    result = await fixed_vs_variable(
        db_session,
        month="2026-05",
        account_id=acc.id,
    )

    assert result.fixed_total == Decimal("500.00")


@pytest.mark.asyncio
async def test_fixed_vs_variable_account_not_found(db_session: AsyncSession) -> None:
    with pytest.raises(AccountNotFound):
        await fixed_vs_variable(db_session, month="2026-05", account_id=99999)
