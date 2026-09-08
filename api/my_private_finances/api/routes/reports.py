from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter
from fastapi.params import Query

from my_private_finances.deps import SessionDep
from my_private_finances.schemas import (
    BudgetComparison,
    FixedVsVariableReport,
    MonthlyReport,
)
from my_private_finances.services import reporting

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/monthly", response_model=MonthlyReport)
async def get_monthly_report(
    month: Annotated[str, Query(min_length=7, max_length=7)],
    session: SessionDep,
    account_id: Annotated[Optional[int], Query(ge=1)] = None,
) -> MonthlyReport:
    return await reporting.monthly_report(session, month=month, account_id=account_id)


@router.get("/budget-vs-actual", response_model=list[BudgetComparison])
async def get_budget_vs_actual(
    month: Annotated[str, Query(min_length=7, max_length=7)],
    session: SessionDep,
    account_id: Annotated[Optional[int], Query(ge=1)] = None,
) -> list[BudgetComparison]:
    return await reporting.budget_vs_actual(session, month=month, account_id=account_id)


@router.get("/fixed-vs-variable", response_model=FixedVsVariableReport)
async def get_fixed_vs_variable(
    month: Annotated[str, Query(min_length=7, max_length=7)],
    session: SessionDep,
    account_id: Annotated[Optional[int], Query(ge=1)] = None,
) -> FixedVsVariableReport:
    return await reporting.fixed_vs_variable(
        session, month=month, account_id=account_id
    )
