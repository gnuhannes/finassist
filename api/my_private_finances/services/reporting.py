"""Reporting aggregations (review finding A1 / issue #104).

All the monthly / annual / trend / net-worth SQL used to live inline in the
route handlers. It now lives here as plain ``async`` functions that take an
``AsyncSession`` and return the typed response schemas; the routes are thin
adapters. Shared filter-building (the ``is_transfer`` guard, the month window,
the account scope) is defined once in :func:`non_transfer_filter`.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional, cast

from sqlalchemy import ColumnElement, and_, case, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from my_private_finances.models import Account, Budget, Category, Transaction
from my_private_finances.schemas import (
    AccountBalancePoint,
    AccountNetWorthSummary,
    AnnualReport,
    BudgetComparison,
    CategoryTotal,
    CategoryTrendItem,
    CostTypeBreakdown,
    FixedVsVariableReport,
    MonthlyReport,
    MonthSummary,
    NetWorthPoint,
    NetWorthReport,
    PayeeTotal,
    SpendingTrendReport,
    TopSpending,
)
from my_private_finances.utils.money import money_from_db

_ZERO = Decimal("0")
_CENTS = Decimal("0.01")
_HUNDRED = Decimal("100")


class ReportError(Exception):
    """Base class for reporting input errors; carries an HTTP status code."""

    status_code = 400


class InvalidMonth(ReportError):
    status_code = 422


class AccountNotFound(ReportError):
    status_code = 404


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #

_TX = cast(Any, Transaction).__table__
_CAT = cast(Any, Category).__table__
_BUDGET = cast(Any, Budget).__table__


def parse_month(value: str) -> tuple[date, date]:
    """Parse ``"YYYY-MM"`` into a ``[start, end)`` half-open date range."""
    try:
        year_str, month_str = value.split("-")
        year = int(year_str)
        month = int(month_str)
    except ValueError as e:
        raise InvalidMonth("month must be in YYYY-MM") from e

    if month < 1 or month > 12:
        raise InvalidMonth("month must be in [1-12]")

    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


async def resolve_currency(session: AsyncSession, account_id: Optional[int]) -> str:
    """Currency for a single account, or ``"EUR"`` when aggregating all accounts."""
    if account_id is None:
        return "EUR"
    res = await session.execute(select(Account).where(Account.id == account_id))  # type: ignore[arg-type]
    acc = res.scalar_one_or_none()
    if acc is None:
        raise AccountNotFound("Account not found")
    return acc.currency


async def _require_account(session: AsyncSession, account_id: Optional[int]) -> None:
    if account_id is None:
        return
    res = await session.execute(select(Account).where(Account.id == account_id))  # type: ignore[arg-type]
    if res.scalar_one_or_none() is None:
        raise AccountNotFound("Account not found")


def non_transfer_filter(
    *,
    account_id: Optional[int],
    start: date,
    end: date,
    expenses_only: bool = False,
) -> ColumnElement[bool]:
    """The filter every report shares: non-transfer rows in ``[start, end)``,
    optionally scoped to one account and/or restricted to expenses."""
    conditions: list[Any] = [
        _TX.c.booking_date >= start,
        _TX.c.booking_date < end,
        _TX.c.is_transfer == False,  # noqa: E712
    ]
    if account_id is not None:
        conditions.append(_TX.c.account_id == account_id)
    if expenses_only:
        conditions.append(_TX.c.amount < 0)
    return and_(*conditions)


# --------------------------------------------------------------------------- #
# Monthly report
# --------------------------------------------------------------------------- #


async def monthly_report(
    session: AsyncSession,
    *,
    month: str,
    account_id: Optional[int] = None,
) -> MonthlyReport:
    start, end = parse_month(month)
    currency = await resolve_currency(session, account_id)

    base_filter = non_transfer_filter(account_id=account_id, start=start, end=end)
    expense_filter = and_(base_filter, _TX.c.amount < 0)

    totals_row = (
        await session.execute(
            select(
                func.count(literal(1)).label("tx_count"),
                func.coalesce(func.sum(_TX.c.amount), 0).label("net_total"),
                func.coalesce(
                    func.sum(case((_TX.c.amount > 0, _TX.c.amount), else_=0)), 0
                ).label("income_total"),
                func.coalesce(
                    func.sum(case((_TX.c.amount < 0, _TX.c.amount), else_=0)), 0
                ).label("expense_total"),
            ).where(base_filter)
        )
    ).one()

    payees_rows = (
        await session.execute(
            select(
                _TX.c.payee,
                func.coalesce(func.sum(_TX.c.amount), 0).label("total"),
            )
            .where(expense_filter)
            .group_by(_TX.c.payee)
            .order_by(func.sum(_TX.c.amount).asc())
            .limit(15)
        )
    ).all()

    cat_rows = (
        await session.execute(
            select(
                _CAT.c.name.label("category_name"),
                func.coalesce(func.sum(_TX.c.amount), 0).label("total"),
            )
            .select_from(_TX.outerjoin(_CAT, _TX.c.category_id == _CAT.c.id))
            .where(expense_filter)
            .group_by(_TX.c.category_id)
            .order_by(func.sum(_TX.c.amount).asc())
        )
    ).all()

    spending_rows = (
        await session.execute(
            select(
                _TX.c.booking_date,
                _TX.c.payee,
                _TX.c.purpose,
                _TX.c.amount,
                _CAT.c.name.label("category_name"),
            )
            .select_from(_TX.outerjoin(_CAT, _TX.c.category_id == _CAT.c.id))
            .where(expense_filter)
            .order_by(_TX.c.amount.asc())
            .limit(10)
        )
    ).all()

    return MonthlyReport(
        account_id=account_id,
        month=month,
        currency=currency,
        transactions_count=int(totals_row.tx_count),
        income_total=money_from_db(totals_row.income_total),
        expense_total=money_from_db(totals_row.expense_total),
        net_total=money_from_db(totals_row.net_total),
        top_payees=[
            PayeeTotal(payee=r.payee, total=money_from_db(r.total)) for r in payees_rows
        ],
        category_breakdown=[
            CategoryTotal(category_name=r.category_name, total=money_from_db(r.total))
            for r in cat_rows
        ],
        top_spendings=[
            TopSpending(
                booking_date=r.booking_date,
                payee=r.payee,
                purpose=r.purpose,
                amount=money_from_db(r.amount),
                category_name=r.category_name,
            )
            for r in spending_rows
        ],
    )


# --------------------------------------------------------------------------- #
# Budget vs actual
# --------------------------------------------------------------------------- #


async def budget_vs_actual(
    session: AsyncSession,
    *,
    month: str,
    account_id: Optional[int] = None,
) -> list[BudgetComparison]:
    start, end = parse_month(month)
    await _require_account(session, account_id)

    budget_rows = (
        await session.execute(
            select(
                _BUDGET.c.category_id,
                _CAT.c.name.label("category_name"),
                _BUDGET.c.amount.label("budgeted"),
            )
            .join(_CAT, _BUDGET.c.category_id == _CAT.c.id)
            .order_by(_CAT.c.name)
        )
    ).all()
    if not budget_rows:
        return []

    actual_rows = (
        await session.execute(
            select(
                _TX.c.category_id,
                func.coalesce(func.sum(_TX.c.amount), 0).label("actual"),
            )
            .where(
                non_transfer_filter(
                    account_id=account_id, start=start, end=end, expenses_only=True
                )
            )
            .group_by(_TX.c.category_id)
        )
    ).all()
    actuals = {r.category_id: money_from_db(r.actual) for r in actual_rows}

    result: list[BudgetComparison] = []
    for row in budget_rows:
        actual = abs(actuals.get(row.category_id, _ZERO))
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


# --------------------------------------------------------------------------- #
# Fixed vs variable
# --------------------------------------------------------------------------- #


async def fixed_vs_variable(
    session: AsyncSession,
    *,
    month: str,
    account_id: Optional[int] = None,
) -> FixedVsVariableReport:
    start, end = parse_month(month)
    currency = await resolve_currency(session, account_id)

    rows = (
        await session.execute(
            select(
                _CAT.c.cost_type,
                func.coalesce(func.sum(_TX.c.amount), 0).label("total"),
                func.count(func.distinct(_CAT.c.id)).label("category_count"),
            )
            .select_from(_TX.outerjoin(_CAT, _TX.c.category_id == _CAT.c.id))
            .where(
                non_transfer_filter(
                    account_id=account_id, start=start, end=end, expenses_only=True
                )
            )
            .group_by(_CAT.c.cost_type)
        )
    ).all()

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
        fixed_total=totals.get("fixed", _ZERO),
        variable_total=totals.get("variable", _ZERO),
        unclassified_total=totals.get(None, _ZERO),
        breakdown=breakdown,
    )


# --------------------------------------------------------------------------- #
# Spending trend
# --------------------------------------------------------------------------- #


async def spending_trend(
    session: AsyncSession,
    *,
    month: str,
    lookback_months: int = 3,
    account_id: Optional[int] = None,
) -> SpendingTrendReport:
    month_start, month_end = parse_month(month)
    currency = await resolve_currency(session, account_id)

    lb_year = month_start.year
    lb_month = month_start.month - lookback_months
    while lb_month <= 0:
        lb_month += 12
        lb_year -= 1
    lookback_start = date(lb_year, lb_month, 1)

    rows = (
        await session.execute(
            select(
                _TX.c.booking_date,
                _TX.c.category_id,
                _CAT.c.name.label("category_name"),
                _TX.c.amount,
            )
            .select_from(_TX.outerjoin(_CAT, _TX.c.category_id == _CAT.c.id))
            .where(
                non_transfer_filter(
                    account_id=account_id,
                    start=lookback_start,
                    end=month_end,
                    expenses_only=True,
                )
            )
        )
    ).all()

    lookback_by_cat: dict[int | None, dict[str, Decimal]] = {}
    current_by_cat: dict[int | None, Decimal] = {}
    cat_names: dict[int | None, str | None] = {}

    for row in rows:
        bdate: date = row.booking_date
        cat_id: int | None = row.category_id
        amount = money_from_db(row.amount)
        cat_names[cat_id] = row.category_name

        if bdate < month_start:
            month_str = f"{bdate.year}-{bdate.month:02d}"
            per_month = lookback_by_cat.setdefault(cat_id, {})
            per_month[month_str] = per_month.get(month_str, _ZERO) + amount
        else:
            current_by_cat[cat_id] = current_by_cat.get(cat_id, _ZERO) + amount

    today = date.today()
    days_in_month = calendar.monthrange(month_start.year, month_start.month)[1]
    days_elapsed = days_in_month if today >= month_end else max(today.day, 1)
    projection_factor = Decimal(days_in_month) / Decimal(days_elapsed)

    categories: list[CategoryTrendItem] = []
    for cat_id in set(lookback_by_cat) | set(current_by_cat):
        lookback_sum = sum(lookback_by_cat.get(cat_id, {}).values(), _ZERO)
        avg_monthly = abs(lookback_sum) / Decimal(lookback_months)
        current_month = abs(current_by_cat.get(cat_id, _ZERO))
        projected = (current_month * projection_factor).quantize(_CENTS)
        categories.append(
            CategoryTrendItem(
                category_name=cat_names.get(cat_id),
                avg_monthly=avg_monthly.quantize(_CENTS),
                current_month=current_month.quantize(_CENTS),
                projected=projected,
            )
        )

    categories.sort(key=lambda c: c.avg_monthly, reverse=True)

    return SpendingTrendReport(
        account_id=account_id,
        month=month,
        lookback_months=lookback_months,
        currency=currency,
        total_avg_monthly=sum((c.avg_monthly for c in categories), _ZERO).quantize(
            _CENTS
        ),
        total_current_month=sum((c.current_month for c in categories), _ZERO).quantize(
            _CENTS
        ),
        total_projected=sum((c.projected for c in categories), _ZERO).quantize(_CENTS),
        categories=categories,
    )


# --------------------------------------------------------------------------- #
# Annual report
# --------------------------------------------------------------------------- #


async def annual_report(
    session: AsyncSession,
    *,
    year: Optional[int] = None,
    account_id: Optional[int] = None,
) -> AnnualReport:
    if year is None:
        year = date.today().year

    year_start = date(year, 1, 1)
    year_end = date(year + 1, 1, 1)
    currency = await resolve_currency(session, account_id)

    rows = (
        await session.execute(
            select(_TX.c.booking_date, _TX.c.amount).where(
                non_transfer_filter(
                    account_id=account_id, start=year_start, end=year_end
                )
            )
        )
    ).all()

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

    months: list[MonthSummary] = []
    for m in range(1, 13):
        month_str = f"{year}-{m:02d}"
        income = income_by_month.get(month_str, _ZERO)
        expenses = expenses_by_month.get(month_str, _ZERO)
        net = income - expenses
        savings_rate = (
            (net / income * _HUNDRED).quantize(_CENTS)
            if income > _ZERO
            else _ZERO.quantize(_CENTS)
        )
        months.append(
            MonthSummary(
                month=month_str,
                income=income.quantize(_CENTS),
                expenses=expenses.quantize(_CENTS),
                net=net.quantize(_CENTS),
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
        ).quantize(_CENTS)
        if months_with_income
        else _ZERO
    )

    return AnnualReport(
        year=year,
        account_id=account_id,
        currency=currency,
        total_income=total_income.quantize(_CENTS),
        total_expenses=total_expenses.quantize(_CENTS),
        total_net=total_net.quantize(_CENTS),
        avg_savings_rate=avg_savings_rate,
        months=months,
    )


# --------------------------------------------------------------------------- #
# Net worth
# --------------------------------------------------------------------------- #


def _month_end(year: int, month: int) -> date:
    if month == 12:
        return date(year + 1, 1, 1) - timedelta(days=1)
    return date(year, month + 1, 1) - timedelta(days=1)


def _month_key(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def _target_months(months: int) -> list[date]:
    """The last N month-end dates, oldest first."""
    today = date.today()
    results: list[date] = []
    for i in range(months - 1, -1, -1):
        year = today.year
        month = today.month - i
        while month <= 0:
            month += 12
            year -= 1
        results.append(_month_end(year, month))
    return results


async def net_worth_report(
    session: AsyncSession,
    *,
    months: int = 12,
) -> NetWorthReport:
    res = await session.execute(
        select(Account)  # type: ignore[arg-type]
        .where(Account.opening_balance.is_not(None))  # type: ignore[union-attr]
        .order_by(Account.id)  # type: ignore[arg-type]
    )
    accounts = list(res.scalars().all())

    if not accounts:
        return NetWorthReport(
            currency="EUR",
            current_total=_ZERO,
            month_over_month_change=_ZERO,
            accounts=[],
            history=[],
        )

    target_month_ends = _target_months(months)
    earliest_date = min(a.opening_balance_date for a in accounts)  # type: ignore[type-var]

    tx_rows = (
        await session.execute(
            select(_TX.c.account_id, _TX.c.booking_date, _TX.c.amount)
            .where(
                _TX.c.account_id.in_([a.id for a in accounts])
                & (_TX.c.booking_date >= earliest_date)
                & (_TX.c.is_transfer == False)  # noqa: E712
            )
            .order_by(_TX.c.booking_date)
        )
    ).all()

    tx_by_account: dict[int, list[tuple[date, Decimal]]] = {
        a.id: [] for a in accounts if a.id is not None
    }
    for row in tx_rows:
        tx_by_account[row.account_id].append(
            (row.booking_date, money_from_db(row.amount))
        )

    balance_series: dict[int, dict[date, Decimal]] = {}
    for acc in accounts:
        assert acc.id is not None
        assert acc.opening_balance is not None
        assert acc.opening_balance_date is not None
        txs = tx_by_account[acc.id]
        balances: dict[date, Decimal] = {}
        for month_end in target_month_ends:
            total = sum(
                (amt for d, amt in txs if acc.opening_balance_date <= d <= month_end),
                _ZERO,
            )
            balances[month_end] = acc.opening_balance + total
        balance_series[acc.id] = balances

    history: list[NetWorthPoint] = []
    for month_end in target_month_ends:
        by_account: list[AccountBalancePoint] = []
        total = _ZERO
        for acc in accounts:
            assert acc.id is not None
            bal = balance_series[acc.id].get(month_end, _ZERO)
            if (
                acc.opening_balance_date is not None
                and month_end >= acc.opening_balance_date
            ):
                by_account.append(AccountBalancePoint(account_id=acc.id, balance=bal))
                total += bal
        history.append(
            NetWorthPoint(
                month=_month_key(month_end), total=total, by_account=by_account
            )
        )

    current_total = history[-1].total if history else _ZERO
    prev_total = history[-2].total if len(history) >= 2 else _ZERO

    account_summaries: list[AccountNetWorthSummary] = []
    for acc in accounts:
        assert acc.id is not None
        assert acc.opening_balance is not None
        assert acc.opening_balance_date is not None
        current_bal = balance_series[acc.id].get(
            target_month_ends[-1], acc.opening_balance
        )
        prev_bal = (
            balance_series[acc.id].get(target_month_ends[-2], acc.opening_balance)
            if len(target_month_ends) >= 2
            else acc.opening_balance
        )
        account_summaries.append(
            AccountNetWorthSummary(
                account_id=acc.id,
                account_name=acc.name,
                currency=acc.currency,
                opening_balance=acc.opening_balance,
                opening_balance_date=acc.opening_balance_date,
                current_balance=current_bal,
                month_over_month_change=current_bal - prev_bal,
            )
        )

    return NetWorthReport(
        currency=accounts[0].currency,
        current_total=current_total,
        month_over_month_change=current_total - prev_total,
        accounts=account_summaries,
        history=history,
    )
