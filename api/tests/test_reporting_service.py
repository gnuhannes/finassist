"""Service-level tests for my_private_finances.services.reporting (issue #104).

These call the aggregation functions directly (not via HTTP) so the branch
coverage registers with pytest-cov.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from my_private_finances.models import Account, Category, Transaction
from my_private_finances.services import reporting
from my_private_finances.services.reporting import AccountNotFound


async def _account(
    session: AsyncSession,
    *,
    name: str = "Main",
    currency: str = "EUR",
    opening_balance: str | None = None,
    opening_balance_date: date | None = None,
) -> Account:
    acc = Account(
        name=name,
        currency=currency,
        opening_balance=Decimal(opening_balance) if opening_balance else None,
        opening_balance_date=opening_balance_date,
    )
    session.add(acc)
    await session.commit()
    await session.refresh(acc)
    return acc


async def _category(
    session: AsyncSession, name: str, cost_type: str | None = None
) -> Category:
    cat = Category(name=name, cost_type=cost_type)
    session.add(cat)
    await session.commit()
    await session.refresh(cat)
    return cat


_HASH = 0


def _tx(
    account_id: int,
    booking_date: date,
    amount: str,
    *,
    category_id: int | None = None,
    payee: str = "Shop",
    is_transfer: bool = False,
) -> Transaction:
    global _HASH
    _HASH += 1
    return Transaction(
        account_id=account_id,
        booking_date=booking_date,
        amount=Decimal(amount),
        currency="EUR",
        payee=payee,
        purpose="p",
        import_source="manual",
        import_hash=f"rs-{_HASH}",
        category_id=category_id,
        is_transfer=is_transfer,
    )


@pytest.mark.asyncio
async def test_monthly_report_aggregates_and_filters(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    other = await _account(db_session, name="Other")
    cat = await _category(db_session, "Groceries")
    db_session.add_all(
        [
            _tx(acc.id, date(2026, 2, 3), "-12.34", category_id=cat.id, payee="REWE"),
            _tx(acc.id, date(2026, 2, 4), "2500.00", payee="Employer"),
            _tx(acc.id, date(2026, 1, 15), "-99.99"),  # other month
            _tx(acc.id, date(2026, 2, 9), "-500.00", is_transfer=True),  # excluded
            _tx(other.id, date(2026, 2, 9), "-1.00"),  # other account
        ]
    )
    await db_session.commit()

    report = await reporting.monthly_report(
        db_session, month="2026-02", account_id=acc.id
    )
    assert report.currency == "EUR"
    assert report.transactions_count == 2
    assert report.income_total == Decimal("2500.00")
    assert report.expense_total == Decimal("-12.34")
    assert report.net_total == Decimal("2487.66")
    assert report.category_breakdown[0].category_name == "Groceries"
    assert report.top_spendings[0].payee == "REWE"


@pytest.mark.asyncio
async def test_monthly_report_all_accounts_defaults_to_eur(
    db_session: AsyncSession,
) -> None:
    await _account(db_session, currency="USD")
    report = await reporting.monthly_report(db_session, month="2026-02")
    assert report.currency == "EUR"
    assert report.account_id is None


@pytest.mark.asyncio
async def test_monthly_report_unknown_account(db_session: AsyncSession) -> None:
    with pytest.raises(AccountNotFound):
        await reporting.monthly_report(db_session, month="2026-02", account_id=4242)


@pytest.mark.asyncio
async def test_spending_trend_averages(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    cat = await _category(db_session, "Food")
    for d, amt in [
        (date(2025, 11, 5), "-100.00"),
        (date(2025, 12, 5), "-200.00"),
        (date(2026, 1, 5), "-300.00"),
        (date(2026, 2, 5), "-150.00"),
    ]:
        db_session.add(_tx(acc.id, d, amt, category_id=cat.id))
    await db_session.commit()

    report = await reporting.spending_trend(
        db_session, month="2026-02", lookback_months=3, account_id=acc.id
    )
    assert len(report.categories) == 1
    item = report.categories[0]
    assert item.category_name == "Food"
    assert item.avg_monthly == Decimal("200.00")
    assert item.current_month == Decimal("150.00")
    assert item.projected >= item.current_month


@pytest.mark.asyncio
async def test_spending_trend_empty(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    report = await reporting.spending_trend(
        db_session, month="2026-02", account_id=acc.id
    )
    assert report.categories == []
    assert report.total_avg_monthly == Decimal("0.00")


@pytest.mark.asyncio
async def test_annual_report_monthly_breakdown(db_session: AsyncSession) -> None:
    acc = await _account(db_session)
    db_session.add_all(
        [
            _tx(acc.id, date(2026, 1, 5), "2500.00"),
            _tx(acc.id, date(2026, 1, 20), "-800.00"),
            _tx(acc.id, date(2025, 12, 31), "-999.00"),  # other year
            _tx(acc.id, date(2026, 3, 3), "-100.00", is_transfer=True),  # excluded
        ]
    )
    await db_session.commit()

    report = await reporting.annual_report(db_session, year=2026, account_id=acc.id)
    assert len(report.months) == 12
    jan = next(m for m in report.months if m.month == "2026-01")
    assert jan.income == Decimal("2500.00")
    assert jan.expenses == Decimal("800.00")
    assert jan.net == Decimal("1700.00")
    assert jan.savings_rate == Decimal("68.00")
    assert report.total_expenses == Decimal("800.00")


@pytest.mark.asyncio
async def test_annual_report_defaults_year_and_validates_account(
    db_session: AsyncSession,
) -> None:
    report = await reporting.annual_report(db_session)
    assert report.year == date.today().year
    with pytest.raises(AccountNotFound):
        await reporting.annual_report(db_session, year=2026, account_id=999)


@pytest.mark.asyncio
async def test_net_worth_report_no_accounts(db_session: AsyncSession) -> None:
    report = await reporting.net_worth_report(db_session, months=6)
    assert report.current_total == Decimal("0")
    assert report.accounts == []
    assert report.history == []


@pytest.mark.asyncio
async def test_net_worth_report_with_opening_balance(db_session: AsyncSession) -> None:
    acc = await _account(
        db_session,
        opening_balance="1000.00",
        opening_balance_date=date(2026, 1, 1),
    )
    db_session.add_all(
        [
            _tx(acc.id, date(2026, 1, 10), "500.00"),
            _tx(acc.id, date(2026, 1, 20), "-200.00"),
            _tx(acc.id, date(2026, 1, 15), "-50.00", is_transfer=True),  # excluded
        ]
    )
    await db_session.commit()

    report = await reporting.net_worth_report(db_session, months=3)
    assert len(report.accounts) == 1
    summary = report.accounts[0]
    assert summary.opening_balance == Decimal("1000.00")
    # 1000 + 500 - 200 = 1300 (transfer excluded)
    assert summary.current_balance == Decimal("1300.00")
    assert report.current_total == Decimal("1300.00")
    assert report.history[-1].month == reporting._month_key(
        reporting._target_months(3)[-1]
    )
