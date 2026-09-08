from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Optional, cast

from fastapi import APIRouter, HTTPException
from fastapi.params import Query
from sqlalchemy import case, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from my_private_finances.utils.money import money_from_db
from my_private_finances.deps import SessionDep
from my_private_finances.models import Account, Budget, Category, Transaction
from my_private_finances.schemas import (
    BudgetComparison,
    CategoryTotal,
    CostTypeBreakdown,
    FixedVsVariableReport,
    MonthlyReport,
    PayeeTotal,
    TopSpending,
)

router = APIRouter(prefix="/reports", tags=["reports"])


def _parse_month(value: str) -> tuple[date, date]:
    try:
        year_str, month_str = value.split("-")
        year = int(year_str)
        month = int(month_str)
    except ValueError as e:
        raise HTTPException(status_code=422, detail="month must be in YYYY-MM") from e

    if month < 1 or month > 12:
        raise HTTPException(status_code=422, detail="month must be in [1-12]")

    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


async def _resolve_currency(session: AsyncSession, account_id: Optional[int]) -> str:
    """Return currency for a single account, or 'EUR' when aggregating all accounts."""
    if account_id is None:
        return "EUR"
    res = await session.execute(select(Account).where(Account.id == account_id))  # type: ignore[arg-type]
    acc = res.scalar_one_or_none()
    if acc is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return acc.currency


@router.get("/monthly", response_model=MonthlyReport)
async def get_monthly_report(
    month: Annotated[str, Query(min_length=7, max_length=7)],
    session: SessionDep,
    account_id: Annotated[Optional[int], Query(ge=1)] = None,
) -> MonthlyReport:
    start, end = _parse_month(month)
    currency = await _resolve_currency(session, account_id)

    tx = cast(Any, Transaction).__table__

    date_filter = (tx.c.booking_date >= start) & (tx.c.booking_date < end)
    transfer_filter = tx.c.is_transfer == False  # noqa: E712
    if account_id is not None:
        base_filter = (tx.c.account_id == account_id) & date_filter & transfer_filter
    else:
        base_filter = date_filter & transfer_filter

    stmt_totals = select(
        func.count(literal(1)).label("tx_count"),
        func.coalesce(func.sum(tx.c.amount), 0).label("net_total"),
        func.coalesce(
            func.sum(case((tx.c.amount > 0, tx.c.amount), else_=0)),
            0,
        ).label("income_total"),
        func.coalesce(
            func.sum(case((tx.c.amount < 0, tx.c.amount), else_=0)),
            0,
        ).label("expense_total"),
    ).where(base_filter)

    totals_row = (await session.execute(stmt_totals)).one()
    tx_count = int(totals_row.tx_count)
    net_total = money_from_db(totals_row.net_total)
    income_total = money_from_db(totals_row.income_total)
    expense_total = money_from_db(totals_row.expense_total)

    stmt_payees = (
        select(
            tx.c.payee,
            func.coalesce(func.sum(tx.c.amount), 0).label("total"),
        )
        .where(base_filter)
        .where(tx.c.amount < 0)
        .group_by(tx.c.payee)
        .order_by(func.sum(tx.c.amount).asc())
        .limit(15)
    )

    payees_rows = (await session.execute(stmt_payees)).all()
    payees = [
        PayeeTotal(payee=r.payee, total=money_from_db(r.total)) for r in payees_rows
    ]

    cat = cast(Any, Category).__table__
    stmt_categories = (
        select(
            cat.c.name.label("category_name"),
            func.coalesce(func.sum(tx.c.amount), 0).label("total"),
        )
        .select_from(tx.outerjoin(cat, tx.c.category_id == cat.c.id))
        .where(base_filter)
        .where(tx.c.amount < 0)
        .group_by(tx.c.category_id)
        .order_by(func.sum(tx.c.amount).asc())
    )

    cat_rows = (await session.execute(stmt_categories)).all()
    categories = [
        CategoryTotal(
            category_name=r.category_name,
            total=money_from_db(r.total),
        )
        for r in cat_rows
    ]

    stmt_top_spendings = (
        select(
            tx.c.booking_date,
            tx.c.payee,
            tx.c.purpose,
            tx.c.amount,
            cat.c.name.label("category_name"),
        )
        .select_from(tx.outerjoin(cat, tx.c.category_id == cat.c.id))
        .where(base_filter)
        .where(tx.c.amount < 0)
        .order_by(tx.c.amount.asc())
        .limit(10)
    )

    spending_rows = (await session.execute(stmt_top_spendings)).all()
    spendings = [
        TopSpending(
            booking_date=r.booking_date,
            payee=r.payee,
            purpose=r.purpose,
            amount=money_from_db(r.amount),
            category_name=r.category_name,
        )
        for r in spending_rows
    ]

    return MonthlyReport(
        account_id=account_id,
        month=month,
        currency=currency,
        transactions_count=tx_count,
        income_total=income_total,
        expense_total=expense_total,
        net_total=net_total,
        top_payees=payees,
        category_breakdown=categories,
        top_spendings=spendings,
    )


@router.get("/budget-vs-actual", response_model=list[BudgetComparison])
async def get_budget_vs_actual(
    month: Annotated[str, Query(min_length=7, max_length=7)],
    session: SessionDep,
    account_id: Annotated[Optional[int], Query(ge=1)] = None,
) -> list[BudgetComparison]:
    start, end = _parse_month(month)

    if account_id is not None:
        res_acc = await session.execute(select(Account).where(Account.id == account_id))  # type: ignore[arg-type]
        if res_acc.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Account not found")

    tx = cast(Any, Transaction).__table__
    cat = cast(Any, Category).__table__
    budget_t = cast(Any, Budget).__table__

    # Get all budgets with category names
    stmt_budgets = (
        select(
            budget_t.c.category_id,
            cat.c.name.label("category_name"),
            budget_t.c.amount.label("budgeted"),
        )
        .join(cat, budget_t.c.category_id == cat.c.id)
        .order_by(cat.c.name)
    )
    budget_rows = (await session.execute(stmt_budgets)).all()

    if not budget_rows:
        return []

    # Get actual spending per category for this month
    transfer_filter = tx.c.is_transfer == False  # noqa: E712
    date_filter = (
        (tx.c.booking_date >= start) & (tx.c.booking_date < end) & (tx.c.amount < 0)
    )
    if account_id is not None:
        base_filter = (tx.c.account_id == account_id) & date_filter & transfer_filter
    else:
        base_filter = date_filter & transfer_filter

    stmt_actuals = (
        select(
            tx.c.category_id,
            func.coalesce(func.sum(tx.c.amount), 0).label("actual"),
        )
        .where(base_filter)
        .group_by(tx.c.category_id)
    )
    actual_rows = (await session.execute(stmt_actuals)).all()
    actuals = {r.category_id: money_from_db(r.actual) for r in actual_rows}

    result = []
    for row in budget_rows:
        raw_actual = actuals.get(row.category_id, Decimal("0"))
        actual = abs(raw_actual)
        budgeted = money_from_db(row.budgeted)
        result.append(
            BudgetComparison(
                category_id=row.category_id,
                category_name=row.category_name,
                budgeted=budgeted,
                actual=actual,
                remaining=budgeted - actual,
            )
        )

    return result


@router.get("/fixed-vs-variable", response_model=FixedVsVariableReport)
async def get_fixed_vs_variable(
    month: Annotated[str, Query(min_length=7, max_length=7)],
    session: SessionDep,
    account_id: Annotated[Optional[int], Query(ge=1)] = None,
) -> FixedVsVariableReport:
    start, end = _parse_month(month)
    currency = await _resolve_currency(session, account_id)

    tx = cast(Any, Transaction).__table__
    cat = cast(Any, Category).__table__

    transfer_filter = tx.c.is_transfer == False  # noqa: E712
    date_filter = (
        (tx.c.booking_date >= start) & (tx.c.booking_date < end) & (tx.c.amount < 0)
    )
    if account_id is not None:
        base_filter = (tx.c.account_id == account_id) & date_filter & transfer_filter
    else:
        base_filter = date_filter & transfer_filter

    stmt = (
        select(
            cat.c.cost_type,
            func.coalesce(func.sum(tx.c.amount), 0).label("total"),
            func.count(func.distinct(cat.c.id)).label("category_count"),
        )
        .select_from(tx.outerjoin(cat, tx.c.category_id == cat.c.id))
        .where(base_filter)
        .group_by(cat.c.cost_type)
    )

    rows = (await session.execute(stmt)).all()

    totals: dict[str | None, Decimal] = {}
    breakdown: list[CostTypeBreakdown] = []
    for r in rows:
        total = abs(money_from_db(r.total))
        totals[r.cost_type] = total
        breakdown.append(
            CostTypeBreakdown(
                cost_type=r.cost_type,
                total=total,
                category_count=int(r.category_count),
            )
        )

    return FixedVsVariableReport(
        account_id=account_id,
        month=month,
        currency=currency,
        fixed_total=totals.get("fixed", Decimal("0")),
        variable_total=totals.get("variable", Decimal("0")),
        unclassified_total=totals.get(None, Decimal("0")),
        breakdown=breakdown,
    )
