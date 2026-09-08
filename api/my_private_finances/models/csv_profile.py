from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import JSON, Column, String
from sqlmodel import Field

from my_private_finances.models.mixins import TimestampMixin


class CsvProfile(TimestampMixin, table=True):
    __tablename__ = "csv_profile"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(String(120), nullable=False, unique=True))
    delimiter: str = Field(default=",")
    date_format: str = Field(default="iso")
    decimal_comma: bool = Field(default=False)
    # Maps field name → list of candidate CSV column headers (first match wins).
    # Only overrides are stored; missing fields fall back to DEFAULT_COLUMN_MAP.
    # Example: {"booking_date": ["Buchungstag", "Valutadatum"], "amount": ["Betrag"]}
    column_map: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default="{}"),
    )
    # Include filter: {column: [allowed_values]}. Rows not matching ALL entries are skipped.
    row_filters: Optional[dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    # Exclude filter: {column: [excluded_values]}. Rows matching ANY entry are skipped.
    row_exclude_filters: Optional[dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
