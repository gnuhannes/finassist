from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from my_private_finances.schemas.base import ReadSchema, StrictSchema

FieldName = Literal["payee", "purpose", "amount"]
Operator = Literal[
    "contains",
    "exact",
    "starts_with",
    "ends_with",
    "gt",
    "lt",
    "gte",
    "lte",
    "eq",
]


class RuleCreate(StrictSchema):
    field: FieldName
    operator: Operator
    value: str = Field(min_length=1, max_length=255)
    category_id: int


class RuleUpdate(StrictSchema):
    field: Optional[FieldName] = None
    operator: Optional[Operator] = None
    value: Optional[str] = Field(default=None, min_length=1, max_length=255)
    category_id: Optional[int] = None


class RuleRead(ReadSchema):
    id: int
    position: int
    field: str
    operator: str
    value: str
    category_id: int


class RuleReorder(StrictSchema):
    rule_ids: list[int]


class ApplyResult(BaseModel):
    categorized: int
