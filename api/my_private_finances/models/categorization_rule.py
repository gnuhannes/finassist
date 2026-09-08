from __future__ import annotations

from typing import Optional

from sqlalchemy import Column, Integer, String
from sqlmodel import Field

from my_private_finances.models.mixins import TimestampMixin


class CategorizationRule(TimestampMixin, table=True):
    __tablename__ = "categorization_rule"

    id: Optional[int] = Field(default=None, primary_key=True)
    position: int = Field(
        sa_column=Column(Integer, nullable=False, unique=True, index=True)
    )
    field: str = Field(sa_column=Column(String(20), nullable=False))
    operator: str = Field(sa_column=Column(String(20), nullable=False))
    value: str = Field(sa_column=Column(String(255), nullable=False))
    category_id: int = Field(foreign_key="category.id")
