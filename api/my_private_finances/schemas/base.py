"""Shared base classes for request and response schemas (issue #105).

Policy:

* **Request bodies** (`*Create`, `*Update`, reorder payloads, …) subclass
  :class:`StrictSchema` — unknown fields are rejected (``extra="forbid"``) so a
  typo in a client payload is a 422, not a silent no-op.
* **Responses** (`*Read`, report DTOs, …) subclass :class:`ReadSchema` —
  ``from_attributes=True`` lets a handler ``return`` the ORM object (or
  ``Schema.model_validate(obj)``) instead of hand-writing a field-by-field
  ``_to_read`` mapper. Enrichment mappers (joining a name, computing a derived
  field) still live in the route/service layer.
"""

from typing import Any, cast

from pydantic import BaseModel, ConfigDict
from sqlmodel import SQLModel


class StrictSchema(SQLModel):
    model_config = cast(Any, ConfigDict(extra="forbid"))


class ReadSchema(BaseModel):
    """Base for response models: validated straight from ORM attributes."""

    model_config = ConfigDict(from_attributes=True)
