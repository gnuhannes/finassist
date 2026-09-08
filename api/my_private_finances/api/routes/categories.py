from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from my_private_finances.deps import SessionDep
from my_private_finances.models import Category, Transaction
from my_private_finances.schemas import CategoryCreate, CategoryRead, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["categories"])


def _to_read(cat: Category) -> CategoryRead:
    assert cat.id is not None
    return CategoryRead(
        id=cat.id, name=cat.name, parent_id=cat.parent_id, cost_type=cat.cost_type
    )


@router.post("", response_model=CategoryRead, status_code=201)
async def create_category(
    category: Annotated[CategoryCreate, Body()], session: SessionDep
):
    if category.parent_id is not None:
        parent = await session.get(Category, category.parent_id)
        if parent is None:
            raise HTTPException(status_code=422, detail="parent_id does not exist")

    db_obj = Category(
        name=category.name,
        parent_id=category.parent_id,
        cost_type=category.cost_type,
    )
    session.add(db_obj)
    await session.commit()
    await session.refresh(db_obj)
    return _to_read(db_obj)


@router.get("", response_model=list[CategoryRead])
async def list_categories(session: SessionDep):
    res = await session.execute(select(Category).order_by(Category.name))  # type: ignore[arg-type]
    return [_to_read(c) for c in res.scalars().all()]


@router.patch("/{category_id}", response_model=CategoryRead)
async def update_category(
    category_id: int,
    payload: Annotated[CategoryUpdate, Body()],
    session: SessionDep,
):
    db_obj = await session.get(Category, category_id)
    if db_obj is None:
        raise HTTPException(status_code=404, detail="Category not found")

    if payload.name is not None:
        db_obj.name = payload.name

    if "cost_type" in payload.model_fields_set:
        db_obj.cost_type = payload.cost_type

    if payload.parent_id is not None:
        if payload.parent_id == category_id:
            raise HTTPException(
                status_code=422, detail="Category cannot be its own parent"
            )
        parent = await session.get(Category, payload.parent_id)
        if parent is None:
            raise HTTPException(status_code=422, detail="parent_id does not exist")
        db_obj.parent_id = payload.parent_id

    await session.commit()
    await session.refresh(db_obj)
    return _to_read(db_obj)


@router.delete("/{category_id}", status_code=204)
async def delete_category(category_id: int, session: SessionDep):
    db_obj = await session.get(Category, category_id)
    if db_obj is None:
        raise HTTPException(status_code=404, detail="Category not found")

    # Check if any transactions reference this category
    result = await session.execute(
        select(Transaction.id).where(Transaction.category_id == category_id).limit(1)
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail="Category is in use by transactions and cannot be deleted",
        )

    await session.delete(db_obj)
    try:
        await session.commit()
    except IntegrityError as e:
        # Foreign keys are enforced (PRAGMA foreign_keys=ON): the category is
        # still referenced by a budget, categorization rule, sub-category, or
        # recurring pattern.
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "Category is still referenced (budget, rule, sub-category, or "
                "recurring pattern) and cannot be deleted"
            ),
        ) from e
