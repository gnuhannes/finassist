from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, HTTPException
from sqlmodel import select

from my_private_finances.deps import SessionDep
from my_private_finances.models import Account
from my_private_finances.schemas import AccountCreate, AccountRead, AccountUpdate

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post("", response_model=AccountRead, status_code=201)
async def create_account(
    account: Annotated[AccountCreate, Body()], session: SessionDep
) -> Account:
    db_obj = Account(name=account.name, currency=account.currency)
    session.add(db_obj)
    await session.commit()
    await session.refresh(db_obj)
    return db_obj


@router.get("", response_model=list[AccountRead])
async def list_accounts(session: SessionDep) -> list[Account]:
    res = await session.execute(select(Account).order_by(Account.id))  # type: ignore[arg-type]
    return list(res.scalars().all())


@router.patch("/{account_id}", response_model=AccountRead)
async def update_account(
    account_id: int,
    payload: Annotated[AccountUpdate, Body()],
    session: SessionDep,
) -> Account:
    db_obj = await session.get(Account, account_id)
    if db_obj is None:
        raise HTTPException(status_code=404, detail="Account not found")

    if payload.opening_balance is not None:
        db_obj.opening_balance = payload.opening_balance
    if payload.opening_balance_date is not None:
        db_obj.opening_balance_date = payload.opening_balance_date

    await session.commit()
    await session.refresh(db_obj)
    return db_obj
