"""Unit tests for the extracted CSV row parser (issue #108 / C6)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from my_private_finances.schemas.import_result import ImportErrorDetail
from my_private_finances.services.csv_import import (
    DEFAULT_COLUMN_MAP,
    CsvConfig,
    ParsedRow,
    RowAccumulator,
    RowFailed,
    RowSkipped,
    detect_encoding,
    parse_csv,
    parse_row,
)
from my_private_finances.services.exceptions import CsvFormatError


def _cfg(**over: object) -> CsvConfig:
    return CsvConfig(column_map={**DEFAULT_COLUMN_MAP}, **over)  # type: ignore[arg-type]


def test_parse_row_happy_path() -> None:
    row = {
        "booking_date": "2026-02-03",
        "amount": "-12.34",
        "currency": "eur",
        "payee": "REWE",
        "purpose": "Groceries",
    }
    out = parse_row(row, 2, _cfg())
    assert isinstance(out, ParsedRow)
    assert out.booking_date == date(2026, 2, 3)
    assert out.amount == Decimal("-12.34")
    assert out.currency == "EUR"
    assert out.payee == "REWE"
    assert out.external_id  # fingerprint fallback


def test_parse_row_missing_date_column_fails() -> None:
    out = parse_row({"amount": "-1.00", "currency": "EUR"}, 2, _cfg())
    assert isinstance(out, RowFailed)
    assert out.error.field == "booking_date"


def test_parse_row_bad_date_fails_with_hint() -> None:
    out = parse_row(
        {"booking_date": "03.02.2026", "amount": "-1.00", "currency": "EUR"}, 2, _cfg()
    )
    assert isinstance(out, RowFailed)
    assert "DMY" in (out.error.hint or "")


def test_parse_row_empty_amount_cell_is_skipped() -> None:
    row = {"booking_date": "2026-02-03", "amount": "", "currency": "EUR"}
    assert isinstance(parse_row(row, 2, _cfg()), RowSkipped)


def test_parse_row_missing_amount_column_fails() -> None:
    out = parse_row({"booking_date": "2026-02-03", "currency": "EUR"}, 2, _cfg())
    assert isinstance(out, RowFailed)
    assert out.error.field == "amount"


def test_parse_row_decimal_comma() -> None:
    row = {"booking_date": "2026-02-03", "amount": "1.234,56", "currency": "EUR"}
    out = parse_row(row, 2, _cfg(decimal_comma=True))
    assert isinstance(out, ParsedRow)
    assert out.amount == Decimal("1234.56")


def test_parse_row_exclude_filter_skips() -> None:
    row = {"booking_date": "2026-02-03", "amount": "-1.00", "currency": "EUR", "T": "x"}
    cfg = _cfg(row_exclude_filters={"T": ["x"]})
    assert isinstance(parse_row(row, 2, cfg), RowSkipped)


def test_detect_encoding_utf8_and_cp1252() -> None:
    _text, enc = detect_encoding(b"a,b\n1,2\n")
    assert enc == "utf-8-sig"
    text, enc = detect_encoding("payee\nBr\xfcckner\n".encode("cp1252"))
    assert enc == "cp1252"
    assert "Brückner" in text


def test_detect_encoding_rejects_undecodable() -> None:
    with pytest.raises(CsvFormatError, match="Cannot decode"):
        detect_encoding(b"\x81\x8d")


def test_parse_csv_counts_and_within_file_dedup() -> None:
    text = (
        "booking_date,amount,currency,external_id\n"
        "2026-02-01,-1.00,EUR,a\n"
        "2026-02-01,-1.00,EUR,a\n"  # exact dup
        "bad,-1.00,EUR,b\n"  # failed
        "2026-02-02,-2.00,EUR,c\n"
    )
    pending, acc = parse_csv(
        text, _cfg(), account_id=1, rules=[], max_rows=1000, max_errors=50
    )
    assert acc.total_rows == 4
    assert acc.failed == 1
    assert acc.duplicates == 1
    assert len(pending) == 2


def test_parse_csv_row_cap() -> None:
    text = "booking_date,amount,currency\n" + "2026-02-01,-1.00,EUR\n" * 5
    with pytest.raises(CsvFormatError, match="row"):
        parse_csv(text, _cfg(), account_id=1, rules=[], max_rows=2, max_errors=50)


def test_row_accumulator_bounds_errors_but_counts_all() -> None:
    acc = RowAccumulator(max_errors=1)
    acc.record_error(ImportErrorDetail(row=2, message="a"))
    acc.record_error(ImportErrorDetail(row=3, message="b"))
    result = acc.to_result()
    assert result.failed == 2
    assert len(result.errors) == 1
    assert result.errors_truncated is True
