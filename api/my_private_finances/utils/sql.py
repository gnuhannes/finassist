"""Query-building helpers (review finding C1 / issue #106).

`cast(Any, Model).__table__` appeared ~19 times across the query code. SQLModel
does not expose ``__table__`` to the type checker, and this project doesn't run
the (deprecated) SQLAlchemy mypy plugin, so Core-style selects that need
``func.sum(t.c.amount)`` etc. otherwise reach for a per-call ``cast``.

:func:`table` centralises that into one named, greppable escape hatch. Column
access through the returned object is still ``Any``-typed, but the pattern lives
in exactly one place and can be swapped for a fully-typed implementation if the
tooling improves. Plain ORM selects (``select(Model).where(Model.x == y)``)
should use the model attributes directly and not this helper.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import SQLModel


def table(model: type[SQLModel]) -> Any:
    """Return a model's Core ``Table`` for column-level query building."""
    return model.__table__  # type: ignore[attr-defined]
