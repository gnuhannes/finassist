from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import Column, Date, Numeric, String, UniqueConstraint
from sqlmodel import Field, SQLModel

from my_private_finances.models.mixins import TimestampMixin


class RecurringPatternBase(SQLModel):
    account_id: int = Field(foreign_key="account.id", index=True)
    payee: str = Field(sa_column=Column(String(255), nullable=False))
    typical_amount: Decimal = Field(sa_column=Column(Numeric(14, 2), nullable=False))
    frequency: str = Field(sa_column=Column(String(20), nullable=False))
    confidence: Decimal = Field(sa_column=Column(Numeric(3, 2), nullable=False))
    last_seen: date = Field(sa_column=Column(Date, nullable=False))
    occurrence_count: int = Field(default=0)
    is_active: bool = Field(default=True)
    user_confirmed: bool = Field(default=False)
    category_id: Optional[int] = Field(default=None, foreign_key="category.id")


class RecurringPattern(TimestampMixin, RecurringPatternBase, table=True):
    __tablename__ = "recurring_pattern"

    id: Optional[int] = Field(default=None, primary_key=True)

    __table_args__ = (
        UniqueConstraint(
            "account_id", "payee", "frequency", name="uq_recurring_pattern"
        ),
    )
