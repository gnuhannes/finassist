from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import Column, Date, Numeric, String
from sqlmodel import Field

from my_private_finances.models.mixins import TimestampMixin


class Account(TimestampMixin, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(String(120), nullable=False))
    currency: str = Field(default="EUR", sa_column=Column(String(3), nullable=False))
    opening_balance: Optional[Decimal] = Field(
        default=None, sa_column=Column(Numeric(14, 2), nullable=True)
    )
    opening_balance_date: Optional[date] = Field(
        default=None, sa_column=Column(Date, nullable=True)
    )
