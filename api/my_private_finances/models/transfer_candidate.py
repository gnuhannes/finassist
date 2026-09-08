from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import Column, Numeric, String, UniqueConstraint
from sqlmodel import Field, SQLModel


class TransferCandidate(SQLModel, table=True):
    __tablename__ = "transfer_candidate"

    id: Optional[int] = Field(default=None, primary_key=True)

    # Negative leg (outgoing transaction, e.g. -500 in Account 1)
    from_transaction_id: int = Field(
        foreign_key="transaction.id", ondelete="CASCADE", index=True
    )
    # Positive leg (incoming transaction, e.g. +500 in Account 2)
    to_transaction_id: int = Field(
        foreign_key="transaction.id", ondelete="CASCADE", index=True
    )

    confidence: Decimal = Field(sa_column=Column(Numeric(3, 2), nullable=False))

    # "pending" | "confirmed" | "dismissed"
    status: str = Field(default="pending", sa_column=Column(String(16), nullable=False))

    __table_args__ = (
        UniqueConstraint(
            "from_transaction_id",
            "to_transaction_id",
            name="uq_transfer_candidate_pair",
        ),
    )
