from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Query

from my_private_finances.deps import SessionDep
from my_private_finances.schemas import SpendingTrendReport
from my_private_finances.services import reporting

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/spending-trend", response_model=SpendingTrendReport)
async def get_spending_trend(
    month: Annotated[str, Query(min_length=7, max_length=7)],
    session: SessionDep,
    lookback_months: Annotated[int, Query(ge=1, le=24)] = 3,
    account_id: Annotated[Optional[int], Query(ge=1)] = None,
) -> SpendingTrendReport:
    return await reporting.spending_trend(
        session,
        month=month,
        lookback_months=lookback_months,
        account_id=account_id,
    )
