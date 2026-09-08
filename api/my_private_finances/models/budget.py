from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import Column, Numeric, UniqueConstraint
from sqlmodel import Field, SQLModel

from my_private_finances.models.mixins import TimestampMixin


class BudgetBase(SQLModel):
    category_id: int = Field(foreign_key="category.id")
    amount: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))


class Budget(TimestampMixin, BudgetBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    __table_args__ = (UniqueConstraint("category_id"),)
