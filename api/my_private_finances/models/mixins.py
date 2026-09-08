"""Shared model mixins (review finding C15 / issue #110)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin(SQLModel):
    """Adds server-managed ``created_at`` / ``updated_at`` audit columns.

    ``server_default`` / ``onupdate`` keep the values correct for raw SQL and
    migrations; ``default_factory`` populates them on ORM-created rows before a
    refresh. ``sa_column_kwargs`` (not ``sa_column``) so SQLModel generates a
    distinct Column per table.
    """

    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column_kwargs={"server_default": func.now()},
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        # onupdate is a Python callable (not func.now()) so ORM inserts and
        # updates use the same clock/precision as created_at; server_default
        # is the safety net for rows touched by raw SQL / migrations.
        sa_column_kwargs={"server_default": func.now(), "onupdate": _utcnow},
    )
