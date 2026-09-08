from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, HTTPException
from sqlmodel import func, select

from my_private_finances.deps import SessionDep
from my_private_finances.models import CategorizationRule, Category
from my_private_finances.schemas import (
    ApplyResult,
    RuleCreate,
    RuleRead,
    RuleReorder,
    RuleUpdate,
)
from my_private_finances.services.categorization import apply_rules_to_uncategorized

router = APIRouter(prefix="/categorization-rules", tags=["categorization-rules"])


@router.post("", response_model=RuleRead, status_code=201)
async def create_rule(
    payload: Annotated[RuleCreate, Body()], session: SessionDep
) -> CategorizationRule:
    # Validate category exists
    cat = await session.get(Category, payload.category_id)
    if cat is None:
        raise HTTPException(status_code=422, detail="category_id does not exist")

    # Auto-assign position as max + 1
    result = await session.execute(
        select(func.coalesce(func.max(CategorizationRule.position), 0))
    )
    max_pos = result.scalar_one()
    next_pos: int = max_pos + 1

    db_obj = CategorizationRule(
        position=next_pos,
        field=payload.field,
        operator=payload.operator,
        value=payload.value,
        category_id=payload.category_id,
    )
    session.add(db_obj)
    await session.commit()
    await session.refresh(db_obj)
    return db_obj


@router.get("", response_model=list[RuleRead])
async def list_rules(session: SessionDep) -> list[CategorizationRule]:
    result = await session.execute(
        select(CategorizationRule).order_by(CategorizationRule.position)  # type: ignore[arg-type]
    )
    return list(result.scalars().all())


@router.patch("/{rule_id}", response_model=RuleRead)
async def update_rule(
    rule_id: int,
    payload: Annotated[RuleUpdate, Body()],
    session: SessionDep,
) -> CategorizationRule:
    db_obj = await session.get(CategorizationRule, rule_id)
    if db_obj is None:
        raise HTTPException(status_code=404, detail="Rule not found")

    if payload.field is not None:
        db_obj.field = payload.field
    if payload.operator is not None:
        db_obj.operator = payload.operator
    if payload.value is not None:
        db_obj.value = payload.value
    if payload.category_id is not None:
        cat = await session.get(Category, payload.category_id)
        if cat is None:
            raise HTTPException(status_code=422, detail="category_id does not exist")
        db_obj.category_id = payload.category_id

    await session.commit()
    await session.refresh(db_obj)
    return db_obj


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(rule_id: int, session: SessionDep) -> None:
    db_obj = await session.get(CategorizationRule, rule_id)
    if db_obj is None:
        raise HTTPException(status_code=404, detail="Rule not found")

    await session.delete(db_obj)
    await session.commit()


@router.put("/reorder", response_model=list[RuleRead])
async def reorder_rules(
    payload: Annotated[RuleReorder, Body()], session: SessionDep
) -> list[CategorizationRule]:
    # Load all rules
    result = await session.execute(select(CategorizationRule))
    rules_by_id = {r.id: r for r in result.scalars().all()}

    # Validate all IDs exist and match
    if set(payload.rule_ids) != set(rules_by_id.keys()):
        raise HTTPException(
            status_code=422,
            detail="rule_ids must contain exactly all existing rule IDs",
        )

    # Reassign positions: use negative temporary values to avoid unique constraint
    for idx, rule_id in enumerate(payload.rule_ids):
        rules_by_id[rule_id].position = -(idx + 1)
    await session.flush()

    for idx, rule_id in enumerate(payload.rule_ids):
        rules_by_id[rule_id].position = idx + 1
    await session.commit()

    # Return in new order
    return sorted(rules_by_id.values(), key=lambda r: r.position)


@router.post("/apply", response_model=ApplyResult)
async def apply_rules(session: SessionDep) -> ApplyResult:
    categorized = await apply_rules_to_uncategorized(session)
    return ApplyResult(categorized=categorized)
