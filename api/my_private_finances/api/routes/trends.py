from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Optional, cast

from fastapi import APIRouter, Query
from sqlalchemy import select

from my_private_finances.utils.money import money_from_db
from my_private_finances.api.routes.reports import _parse_month, _resolve_currency
from my_private_finances.deps import SessionDep
from my_private_finances.models import Category, Transaction
from my_private_finances.schemas import CategoryTrendItem, SpendingTrendReport

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/spending-trend", response_model=SpendingTrendReport)
async def get_spending_trend(
    month: Annotated[str, Query(min_length=7, max_length=7)],
    session: SessionDep,
    lookback_months: Annotated[int, Query(ge=1, le=24)] = 3,
    account_id: Annotated[Optional[int], Query(ge=1)] = None,
) -> SpendingTrendReport:
    month_start, month_end = _parse_month(month)
    currency = await _resolve_currency(session, account_id)

    # Compute lookback window: N complete months immediately before month_start
    lookback_end = month_start  # exclusive
    # Go back N months
    lb_year = month_start.year
    lb_month = month_start.month - lookback_months
    while lb_month <= 0:
        lb_month += 12
        lb_year -= 1
    lookback_start = date(lb_year, lb_month, 1)

    tx = cast(Any, Transaction).__table__
    cat = cast(Any, Category).__table__

    # Fetch all expense rows in [lookback_start, month_end)
    transfer_filter = tx.c.is_transfer == False  # noqa: E712
    expense_filter = tx.c.amount < 0
    date_filter = (tx.c.booking_date >= lookback_start) & (
        tx.c.booking_date < month_end
    )

    if account_id is not None:
        base_filter = (
            (tx.c.account_id == account_id)
            & date_filter
            & transfer_filter
            & expense_filter
        )
    else:
        base_filter = date_filter & transfer_filter & expense_filter

    stmt = (
        select(
            tx.c.booking_date,
            tx.c.category_id,
            cat.c.name.label("category_name"),
            tx.c.amount,
        )
        .select_from(tx.outerjoin(cat, tx.c.category_id == cat.c.id))
        .where(base_filter)
    )

    rows = (await session.execute(stmt)).all()

    # Separate into lookback months vs current month
    # Aggregate: per-category, per-month totals for lookback; per-category total for current
    lookback_by_cat: dict[
        int | None, dict[str, Decimal]
    ] = {}  # cat_id -> month_str -> total
    current_by_cat: dict[int | None, Decimal] = {}
    cat_names: dict[int | None, str | None] = {}

    for row in rows:
        bdate: date = row.booking_date
        cat_id: int | None = row.category_id
        cat_name: str | None = row.category_name
        amount = money_from_db(row.amount)

        cat_names[cat_id] = cat_name

        if bdate < lookback_end:
            # lookback month
            month_str = f"{bdate.year}-{bdate.month:02d}"
            if cat_id not in lookback_by_cat:
                lookback_by_cat[cat_id] = {}
            lookback_by_cat[cat_id][month_str] = (
                lookback_by_cat[cat_id].get(month_str, Decimal("0")) + amount
            )
        else:
            # current month
            current_by_cat[cat_id] = current_by_cat.get(cat_id, Decimal("0")) + amount

    # Gather all category IDs
    all_cat_ids = set(lookback_by_cat.keys()) | set(current_by_cat.keys())

    # Compute projection factor
    today = date.today()
    days_in_month = calendar.monthrange(month_start.year, month_start.month)[1]
    if today >= month_end:
        # month is complete
        days_elapsed = days_in_month
    else:
        days_elapsed = max(today.day, 1)
    projection_factor = Decimal(days_in_month) / Decimal(days_elapsed)

    categories: list[CategoryTrendItem] = []
    for cat_id in all_cat_ids:
        name = cat_names.get(cat_id)

        # avg_monthly: sum of monthly totals in lookback / N (as positive)
        monthly_totals = lookback_by_cat.get(cat_id, {})
        lookback_sum = sum(monthly_totals.values(), Decimal("0"))
        avg_monthly = abs(lookback_sum) / Decimal(lookback_months)

        # current_month: actual this month (positive)
        raw_current = current_by_cat.get(cat_id, Decimal("0"))
        current_month = abs(raw_current)

        # projected: current * factor
        projected = (current_month * projection_factor).quantize(Decimal("0.01"))

        categories.append(
            CategoryTrendItem(
                category_name=name,
                avg_monthly=avg_monthly.quantize(Decimal("0.01")),
                current_month=current_month.quantize(Decimal("0.01")),
                projected=projected,
            )
        )

    # Sort by avg_monthly descending (biggest spenders first)
    categories.sort(key=lambda c: c.avg_monthly, reverse=True)

    total_avg = sum((c.avg_monthly for c in categories), Decimal("0"))
    total_current = sum((c.current_month for c in categories), Decimal("0"))
    total_projected = sum((c.projected for c in categories), Decimal("0"))

    return SpendingTrendReport(
        account_id=account_id,
        month=month,
        lookback_months=lookback_months,
        currency=currency,
        total_avg_monthly=total_avg.quantize(Decimal("0.01")),
        total_current_month=total_current.quantize(Decimal("0.01")),
        total_projected=total_projected.quantize(Decimal("0.01")),
        categories=categories,
    )
