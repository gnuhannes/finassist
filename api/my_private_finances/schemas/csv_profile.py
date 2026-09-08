from __future__ import annotations

from pydantic import BaseModel, ConfigDict

# Valid field names that can be remapped via column_map
REMAPPABLE_FIELDS = frozenset(
    {"booking_date", "amount", "currency", "payee", "purpose", "external_id", "notes"}
)


class CsvProfileCreate(BaseModel):
    name: str
    delimiter: str = ","
    date_format: str = "iso"
    decimal_comma: bool = False
    # Keys must be members of REMAPPABLE_FIELDS; values are ordered candidate headers.
    column_map: dict[str, list[str]] = {}
    # Include filter: {column: [allowed_values]}. Rows not matching ALL entries are skipped.
    row_filters: dict[str, list[str]] | None = None
    # Exclude filter: {column: [excluded_values]}. Rows matching ANY entry are skipped.
    row_exclude_filters: dict[str, list[str]] | None = None


class CsvProfileRead(CsvProfileCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


class CsvProfileUpdate(BaseModel):
    name: str | None = None
    delimiter: str | None = None
    date_format: str | None = None
    decimal_comma: bool | None = None
    column_map: dict[str, list[str]] | None = None
    row_filters: dict[str, list[str]] | None = None
    row_exclude_filters: dict[str, list[str]] | None = None
