from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import Field

from my_private_finances.schemas.base import ReadSchema, StrictSchema


class AccountCreate(StrictSchema):
    name: str = Field(min_length=1, max_length=120)
    currency: str = Field(default="EUR", min_length=3, max_length=3)


class AccountUpdate(StrictSchema):
    opening_balance: Optional[Decimal] = None
    opening_balance_date: Optional[date] = None


class AccountRead(ReadSchema):
    id: int
    name: str
    currency: str
    opening_balance: Optional[Decimal] = None
    opening_balance_date: Optional[date] = None
