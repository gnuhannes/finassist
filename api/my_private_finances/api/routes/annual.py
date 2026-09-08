from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Optional, cast

from fastapi import APIRouter, Query
from sqlalchemy import select

from my_private_finances.api.routes.reports import _resolve_currency
from my_private_finances.deps import SessionDep
from my_private_finances.models import Transaction
from my_private_finances.schemas import AnnualReport, MonthSummary
from my_private_finances.utils.money import money_from_db

router = APIRouter(prefix="/reports", tags=["reports"])

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")


@router.get("/annual", response_model=AnnualReport)
async def get_annual_report(
    session: SessionDep,
    year: Annotated[int, Query(ge=2000, le=2100)] = None,  # type: ignore[assignment]
    account_id: Annotated[Optional[int], Query(ge=1)] = None,
) -> AnnualReport:
    if year is None:
        year = date.today().year

    year_start = date(year, 1, 1)
    year_end = date(year + 1, 1, 1)
    currency = await _resolve_currency(session, account_id)

    tx = cast(Any, Transaction).__table__

    transfer_filter = tx.c.is_transfer == False  # noqa: E712
    date_filter = (tx.c.booking_date >= year_start) & (tx.c.booking_date < year_end)

    if account_id is not None:
        base_filter = (tx.c.account_id == account_id) & date_filter & transfer_filter
    else:
        base_filter = date_filter & transfer_filter

    stmt = select(tx.c.booking_date, tx.c.amount).where(base_filter)
    rows = (await session.execute(stmt)).all()

    # Aggregate per month
    income_by_month: dict[str, Decimal] = {}
    expenses_by_month: dict[str, Decimal] = {}

    for row in rows:
        bdate: date = row.booking_date
        month_str = f"{bdate.year}-{bdate.month:02d}"
        amount = money_from_db(row.amount)
        if amount > _ZERO:
            income_by_month[month_str] = income_by_month.get(month_str, _ZERO) + amount
        else:
            expenses_by_month[month_str] = expenses_by_month.get(
                month_str, _ZERO
            ) + abs(amount)

    # Build all 12 months
    months: list[MonthSummary] = []
    for m in range(1, 13):
        month_str = f"{year}-{m:02d}"
        income = income_by_month.get(month_str, _ZERO)
        expenses = expenses_by_month.get(month_str, _ZERO)
        net = income - expenses
        savings_rate = (
            (net / income * _HUNDRED).quantize(Decimal("0.01"))
            if income > _ZERO
            else _ZERO.quantize(Decimal("0.01"))
        )
        months.append(
            MonthSummary(
                month=month_str,
                income=income.quantize(Decimal("0.01")),
                expenses=expenses.quantize(Decimal("0.01")),
                net=net.quantize(Decimal("0.01")),
                savings_rate=savings_rate,
            )
        )

    total_income = sum((m.income for m in months), _ZERO)
    total_expenses = sum((m.expenses for m in months), _ZERO)
    total_net = total_income - total_expenses

    months_with_income = [m for m in months if m.income > _ZERO]
    avg_savings_rate = (
        (
            sum((m.savings_rate for m in months_with_income), _ZERO)
            / Decimal(len(months_with_income))
        ).quantize(Decimal("0.01"))
        if months_with_income
        else _ZERO
    )

    return AnnualReport(
        year=year,
        account_id=account_id,
        currency=currency,
        total_income=total_income.quantize(Decimal("0.01")),
        total_expenses=total_expenses.quantize(Decimal("0.01")),
        total_net=total_net.quantize(Decimal("0.01")),
        avg_savings_rate=avg_savings_rate,
        months=months,
    )
