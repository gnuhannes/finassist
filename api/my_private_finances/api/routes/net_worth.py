"""Net worth report endpoint.

Computes monthly account balances as:
  balance_at_month_end = opening_balance + SUM(non-transfer transactions
                          where booking_date >= opening_balance_date
                          and booking_date <= month_end)

Only accounts with opening_balance set are included.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Any, cast

from fastapi import APIRouter
from fastapi.params import Query
from sqlalchemy import select

from my_private_finances.deps import SessionDep
from my_private_finances.models import Account, Transaction
from my_private_finances.schemas import (
    AccountBalancePoint,
    AccountNetWorthSummary,
    NetWorthPoint,
    NetWorthReport,
)
from my_private_finances.utils.money import money_from_db

router = APIRouter(prefix="/reports", tags=["reports"])


def _month_end(year: int, month: int) -> date:
    """Return the last day of the given month."""
    if month == 12:
        return date(year + 1, 1, 1) - timedelta(days=1)
    return date(year, month + 1, 1) - timedelta(days=1)


def _month_key(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def _target_months(months: int) -> list[date]:
    """Return the last N month-end dates, oldest first."""
    today = date.today()
    results: list[date] = []
    for i in range(months - 1, -1, -1):
        # Go back i months from current month
        year = today.year
        month = today.month - i
        while month <= 0:
            month += 12
            year -= 1
        results.append(_month_end(year, month))
    return results


@router.get("/net-worth", response_model=NetWorthReport)
async def get_net_worth(
    session: SessionDep,
    months: Annotated[int, Query(ge=1, le=60)] = 12,
) -> NetWorthReport:
    # Load accounts with opening_balance configured
    res = await session.execute(
        select(Account)  # type: ignore[arg-type]
        .where(Account.opening_balance.is_not(None))  # type: ignore[union-attr]
        .order_by(Account.id)  # type: ignore[arg-type]
    )
    accounts = list(res.scalars().all())

    if not accounts:
        return NetWorthReport(
            currency="EUR",
            current_total=Decimal("0"),
            month_over_month_change=Decimal("0"),
            accounts=[],
            history=[],
        )

    tx = cast(Any, Transaction).__table__
    target_month_ends = _target_months(months)
    earliest_date = min(a.opening_balance_date for a in accounts)  # type: ignore[type-var]

    # Fetch all relevant transactions for all accounts in one query
    stmt = (
        select(tx.c.account_id, tx.c.booking_date, tx.c.amount)
        .where(
            tx.c.account_id.in_([a.id for a in accounts])
            & (tx.c.booking_date >= earliest_date)
            & (tx.c.is_transfer == False)  # noqa: E712
        )
        .order_by(tx.c.booking_date)
    )
    tx_rows = (await session.execute(stmt)).all()

    # Group transactions by account_id
    tx_by_account: dict[int, list[tuple[date, Decimal]]] = {
        a.id: [] for a in accounts if a.id is not None
    }  # type: ignore[misc]
    for row in tx_rows:
        tx_by_account[row.account_id].append(
            (row.booking_date, money_from_db(row.amount))
        )

    # Build monthly balance series per account
    # balance_at[account_id][month_end_date] = Decimal
    balance_series: dict[int, dict[date, Decimal]] = {}

    for acc in accounts:
        assert acc.id is not None
        assert acc.opening_balance is not None
        assert acc.opening_balance_date is not None

        txs = tx_by_account[acc.id]
        balances: dict[date, Decimal] = {}

        for month_end in target_month_ends:
            # Only include transactions from opening_balance_date up to month_end
            total = sum(
                (amt for d, amt in txs if acc.opening_balance_date <= d <= month_end),
                Decimal("0"),
            )
            balances[month_end] = acc.opening_balance + total

        balance_series[acc.id] = balances

    # Build history (monthly aggregated net worth)
    history: list[NetWorthPoint] = []
    for month_end in target_month_ends:
        by_account: list[AccountBalancePoint] = []
        total = Decimal("0")
        for acc in accounts:
            assert acc.id is not None
            bal = balance_series[acc.id].get(month_end, Decimal("0"))
            # Only include if month_end >= opening_balance_date
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

    # Current totals (last month-end)
    current_total = history[-1].total if history else Decimal("0")
    prev_total = history[-2].total if len(history) >= 2 else Decimal("0")
    mom_change = current_total - prev_total

    # Per-account summaries
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
        currency=accounts[0].currency if accounts else "EUR",
        current_total=current_total,
        month_over_month_change=mom_change,
        accounts=account_summaries,
        history=history,
    )
