"""Unit tests for the CSV value parsers (issue #100, finding C12)."""

from __future__ import annotations

import pytest

from my_private_finances.services.csv_import import _parse_decimal


@pytest.mark.parametrize("value", ["NaN", "nan", "Infinity", "-Infinity", "inf"])
def test_parse_decimal_rejects_non_finite(value: str) -> None:
    with pytest.raises(ValueError):
        _parse_decimal(value, decimal_comma=False)


def test_parse_decimal_accepts_normal_values() -> None:
    assert str(_parse_decimal("-12.34", decimal_comma=False)) == "-12.34"
    assert str(_parse_decimal("1.234,56", decimal_comma=True)) == "1234.56"
