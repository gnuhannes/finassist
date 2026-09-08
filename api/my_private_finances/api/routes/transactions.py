from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.params import Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from my_private_finances.deps import SessionDep
from my_private_finances.models import Category, Transaction
from my_private_finances.schemas import (
    TransactionCreate,
    TransactionListResponse,
    TransactionRead,
    TransactionUpdate,
)
from my_private_finances.services.transaction_hash import HashInput, compute_import_hash
from my_private_finances.utils.db_helpers import get_account_or_404

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("", response_model=TransactionRead, status_code=201)
async def create_transaction(
    tx: TransactionCreate,
    session: SessionDep,
) -> TransactionRead:
    await get_account_or_404(session, tx.account_id)

    if tx.category_id is not None:
        if await session.get(Category, tx.category_id) is None:
            raise HTTPException(status_code=422, detail="Category not found")

    import_hash = compute_import_hash(
        HashInput(
            account_id=tx.account_id,
            booking_date=tx.booking_date,
            amount=tx.amount,
            currency=tx.currency,
            payee=tx.payee,
            purpose=tx.purpose,
            external_id=tx.external_id,
            import_source=tx.import_source,
        )
    )

    db_obj = Transaction(
        account_id=tx.account_id,
        booking_date=tx.booking_date,
        amount=tx.amount,
        currency=tx.currency,
        payee=tx.payee,
        purpose=tx.purpose,
        category_id=tx.category_id,
        external_id=tx.external_id,
        import_source=tx.import_source,
        import_hash=import_hash,
    )

    session.add(db_obj)

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="Duplicate transaction (import_hash)"
        ) from e

    await session.refresh(db_obj)

    if db_obj.id is None:
        raise HTTPException(status_code=500, detail="Transaction ID not assigned")

    return TransactionRead(
        id=db_obj.id,
        account_id=db_obj.account_id,
        booking_date=db_obj.booking_date,
        amount=db_obj.amount,
        currency=db_obj.currency,
        payee=db_obj.payee,
        purpose=db_obj.purpose,
        category_id=db_obj.category_id,
        external_id=db_obj.external_id,
        import_source=db_obj.import_source,
        import_hash=db_obj.import_hash,
        is_transfer=db_obj.is_transfer,
    )


@router.patch("/{transaction_id}", response_model=TransactionRead)
async def update_transaction(
    transaction_id: int,
    payload: TransactionUpdate,
    session: SessionDep,
) -> TransactionRead:
    db_obj = await session.get(Transaction, transaction_id)
    if db_obj is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if payload.category_id is not None:
        cat = await session.get(Category, payload.category_id)
        if cat is None:
            raise HTTPException(status_code=422, detail="Category not found")

    db_obj.category_id = payload.category_id
    await session.commit()
    await session.refresh(db_obj)

    assert db_obj.id is not None
    return TransactionRead(
        id=db_obj.id,
        account_id=db_obj.account_id,
        booking_date=db_obj.booking_date,
        amount=db_obj.amount,
        currency=db_obj.currency,
        payee=db_obj.payee,
        purpose=db_obj.purpose,
        category_id=db_obj.category_id,
        external_id=db_obj.external_id,
        import_source=db_obj.import_source,
        import_hash=db_obj.import_hash,
        is_transfer=db_obj.is_transfer,
    )


@router.get("", response_model=TransactionListResponse)
async def list_transactions(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    account_id: Annotated[Optional[int], Query(ge=1)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    category_filter: str | None = None,
    q: str | None = None,
    amount_min: Decimal | None = None,
    amount_max: Decimal | None = None,
) -> TransactionListResponse:
    filters: list[Any] = []
    if account_id is not None:
        filters.append(Transaction.account_id == account_id)  # type: ignore[arg-type]
    if date_from is not None:
        filters.append(Transaction.booking_date >= date_from)  # type: ignore[arg-type]
    if date_to is not None:
        filters.append(Transaction.booking_date <= date_to)  # type: ignore[arg-type]
    if category_filter == "uncategorized":
        filters.append(Transaction.category_id.is_(None))  # type: ignore[union-attr]
    if q is not None:
        filters.append(
            or_(
                Transaction.payee.ilike(f"%{q}%"),  # type: ignore[union-attr]
                Transaction.purpose.ilike(f"%{q}%"),  # type: ignore[union-attr]
            )
        )
    if amount_min is not None:
        filters.append(Transaction.amount >= amount_min)  # type: ignore[arg-type]
    if amount_max is not None:
        filters.append(Transaction.amount <= amount_max)  # type: ignore[arg-type]

    count_stmt = select(func.count()).select_from(Transaction).where(*filters)  # type: ignore[arg-type]
    total = (await session.execute(count_stmt)).scalar_one()

    stmt = (
        select(Transaction)
        .where(*filters)  # type: ignore[arg-type]
        .order_by(
            Transaction.booking_date.desc(),  # type: ignore[attr-defined]
            Transaction.id.desc(),  # type: ignore[union-attr]
        )
        .limit(limit)
        .offset(offset)
    )

    res = await session.execute(stmt)
    rows = list(res.scalars().all())

    items: list[TransactionRead] = []
    for row in rows:
        if row.id is None:
            continue
        items.append(
            TransactionRead(
                id=row.id,
                account_id=row.account_id,
                booking_date=row.booking_date,
                amount=row.amount,
                currency=row.currency,
                payee=row.payee,
                purpose=row.purpose,
                category_id=row.category_id,
                external_id=row.external_id,
                import_source=row.import_source,
                import_hash=row.import_hash,
                is_transfer=row.is_transfer,
            )
        )

    return TransactionListResponse(items=items, total=total)
