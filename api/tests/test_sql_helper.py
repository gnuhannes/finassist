"""Tests for the `table()` query helper and the C1 escape-hatch budget (#106)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Table

from my_private_finances.models import Transaction
from my_private_finances.utils.sql import table

_PKG_ROOT = Path(__file__).resolve().parent.parent / "my_private_finances"


def test_table_returns_the_core_table() -> None:
    t = table(Transaction)
    assert isinstance(t, Table)
    assert t is Transaction.__table__  # type: ignore[attr-defined]
    # Column-level access still works for Core-style query building.
    assert "amount" in t.c
    assert "is_transfer" in t.c


def test_no_raw_dunder_table_access_outside_the_helper() -> None:
    """`.__table__` must only be reached through `utils/sql.py::table` (C1).

    Keeps the count of the `cast(Any, Model).__table__` escape hatch at its
    documented minimum: one, inside the helper.
    """
    offenders: list[str] = []
    for path in _PKG_ROOT.rglob("*.py"):
        if path.name == "sql.py" and path.parent.name == "utils":
            continue
        if "__table__" in path.read_text():
            offenders.append(str(path.relative_to(_PKG_ROOT)))
    assert not offenders, f"Use utils.sql.table() instead of .__table__ in: {offenders}"
