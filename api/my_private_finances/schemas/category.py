from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from my_private_finances.schemas.base import ReadSchema, StrictSchema

CostType = Literal["fixed", "variable"]


class CategoryCreate(StrictSchema):
    name: str = Field(min_length=1, max_length=120)
    parent_id: Optional[int] = None
    cost_type: Optional[CostType] = None


class CategoryUpdate(StrictSchema):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    parent_id: Optional[int] = None
    cost_type: Optional[CostType] = None


class CategoryRead(ReadSchema):
    id: int
    name: str
    parent_id: Optional[int] = None
    cost_type: Optional[str] = None
