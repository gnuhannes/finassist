from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Query

from my_private_finances.deps import SessionDep
from my_private_finances.schemas import AnnualReport
from my_private_finances.services import reporting

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/annual", response_model=AnnualReport)
async def get_annual_report(
    session: SessionDep,
    year: Annotated[Optional[int], Query(ge=2000, le=2100)] = None,
    account_id: Annotated[Optional[int], Query(ge=1)] = None,
) -> AnnualReport:
    return await reporting.annual_report(session, year=year, account_id=account_id)
