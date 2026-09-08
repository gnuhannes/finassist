from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import field_serializer

from my_private_finances.schemas.base import ReadSchema


class TransactionRead(ReadSchema):
    id: int
    account_id: int
    booking_date: date
    amount: Decimal
    currency: str

    payee: Optional[str] = None
    purpose: Optional[str] = None
    notes: Optional[str] = None

    category_id: Optional[int] = None

    external_id: Optional[str] = None
    import_source: Optional[str] = None
    import_hash: str
    is_transfer: bool = False

    @field_serializer("amount")
    def _serialize_amount(self, value: Decimal) -> str:
        return str(value)
