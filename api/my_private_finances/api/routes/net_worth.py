"""Net worth report endpoint.

Computes monthly account balances as:
  balance_at_month_end = opening_balance + SUM(non-transfer transactions
                          where booking_date >= opening_balance_date
                          and booking_date <= month_end)

Only accounts with opening_balance set are included. The aggregation lives in
``services.reporting.net_worth_report``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter
from fastapi.params import Query

from my_private_finances.deps import SessionDep
from my_private_finances.schemas import NetWorthReport
from my_private_finances.services import reporting

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/net-worth", response_model=NetWorthReport)
async def get_net_worth(
    session: SessionDep,
    months: Annotated[int, Query(ge=1, le=60)] = 12,
) -> NetWorthReport:
    return await reporting.net_worth_report(session, months=months)
