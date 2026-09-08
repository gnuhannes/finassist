from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import Column, Date, Index, Numeric, String, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from my_private_finances.models.mixins import TimestampMixin


class TransactionBase(SQLModel):
    account_id: int = Field(foreign_key="account.id", ondelete="RESTRICT", index=True)

    booking_date: date = Field(sa_column=Column(Date, nullable=False, index=True))

    amount: Decimal = Field(sa_column=Column(Numeric(14, 2), nullable=False))
    currency: str = Field(default="EUR", sa_column=Column(String(3), nullable=False))

    payee: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    purpose: Optional[str] = Field(default=None, sa_column=Column(Text))
    notes: Optional[str] = Field(default=None, sa_column=Column(Text))

    category_id: Optional[int] = Field(
        default=None, foreign_key="category.id", ondelete="SET NULL"
    )

    external_id: Optional[str] = Field(default=None, sa_column=Column(String(128)))
    import_source: Optional[str] = Field(default=None, sa_column=Column(String(64)))

    import_hash: str = Field(sa_column=Column(String(64), nullable=False))


class Transaction(TimestampMixin, TransactionBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    is_transfer: bool = Field(default=False)

    __table_args__ = (
        UniqueConstraint("account_id", "import_hash", name="uq_tx_account_import_hash"),
        Index("ix_tx_account_date", "account_id", "booking_date"),
    )
