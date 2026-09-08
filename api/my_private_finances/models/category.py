from __future__ import annotations

from typing import Optional

from sqlalchemy import Column, String
from sqlmodel import Field, SQLModel

from my_private_finances.models.mixins import TimestampMixin


class CategoryBase(SQLModel):
    name: str = Field(sa_column=Column(String(120), nullable=False, index=True))
    parent_id: Optional[int] = Field(default=None, foreign_key="category.id")
    cost_type: Optional[str] = Field(
        default=None, sa_column=Column(String(10), nullable=True)
    )


class Category(TimestampMixin, CategoryBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
