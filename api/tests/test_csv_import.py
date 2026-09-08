from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient

from my_private_finances.services.csv_import import (
    ColumnMap,
    import_transactions_from_csv_path,
)
from my_private_finances.services.exceptions import CsvFormatError, NotFoundError
from tests.helpers import create_account, create_category, create_rule


@pytest.mark.asyncio
async def test_csv_import_creates_transactions_and_is_idempotent(
    test_app: AsyncClient,
    tmp_path: Path,
) -> None:
    acc = await create_account(test_app)
    account_id = acc["id"]

    csv_content = (
        "booking_date,amount,currency,payee,purpose,external_id\n"
        "2026-01-18,-12.34,EUR,Rewe,Groceries,abc-1\n"
        "2026-01-19,-4.50,EUR,Baecker,Bread,\n"
    )

    csv_file = tmp_path / "import.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    try:
        session_factory = test_app._transport.app.state.session_factory  # type: ignore[attr-defined]
        async with session_factory() as session:  # type: ignore[call-arg]
            res1 = await import_transactions_from_csv_path(
                session=session,
                account_id=account_id,
                csv_path=csv_file,
            )

        assert res1.total_rows == 2, f"Expected 2 total_rows, got {res1}"
        assert res1.created == 2, f"Expected 2 created, got {res1}"
        assert res1.duplicates == 0, f"Expected 0 duplicates, got {res1}"
        assert res1.failed == 0, f"Expected 0 failed, got {res1}"
        assert res1.errors == [], f"Expected no errors, got {res1.errors}"

        async with session_factory() as session:  # type: ignore[call-arg]
            res2 = await import_transactions_from_csv_path(
                session=session,
                account_id=account_id,
                csv_path=csv_file,
            )

        assert res2.total_rows == 2, f"Expected 2 total_rows, got {res2}"
        assert res2.created == 0, f"Expected 0 created on reimport, got {res2}"
        assert res2.duplicates == 2, f"Expected 2 duplicates on reimport, got {res2}"
        assert res2.failed == 0, f"Expected 0 failed, got {res2}"

        res_list = await test_app.get(
            "/api/transactions", params={"account_id": account_id}
        )
        assert res_list.status_code == 200, (
            f"Expected 200, got {res_list.status_code}: {res_list.text}"
        )
        rows = res_list.json()["items"]
        assert len(rows) == 2, f"Expected 2 transactions in DB, got {len(rows)}: {rows}"

        # Map correctness (don't depend on ordering too much; find by external_id or payee)
        by_payee = {r.get("payee"): r for r in rows}

        assert "Rewe" in by_payee, (
            f"Expected a transaction with payee='Rewe', got: {rows}"
        )
        rewe = by_payee["Rewe"]
        assert rewe["booking_date"] == "2026-01-18", f"booking_date mismatch: {rewe}"
        assert rewe["amount"] == "-12.34", f"amount mismatch: {rewe}"
        assert rewe["currency"] == "EUR", f"currency mismatch: {rewe}"
        assert rewe["purpose"] == "Groceries", f"purpose mismatch: {rewe}"
        assert rewe["external_id"] == "abc-1", f"external_id mismatch: {rewe}"
        assert rewe["import_hash"], f"import_hash missing: {rewe}"

        # Row with missing external_id should be generated (non-empty)
        other = next(r for r in rows if r["external_id"] != "abc-1")
        assert other["external_id"], f"Expected generated external_id, got: {other}"
        assert other["import_hash"], f"import_hash missing: {other}"

    finally:
        csv_file.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_csv_import_custom_column_map(
    test_app: AsyncClient,
    tmp_path: Path,
) -> None:
    """column_map overrides let non-standard headers be mapped to transaction fields."""
    acc = await create_account(test_app)
    account_id = acc["id"]

    # CSV uses completely custom header names
    csv_content = (
        "Datum,Wert,Waehrung,Empfaenger,Info\n"
        "2026-02-01,-25.00,EUR,Bäcker,Bread purchase\n"
    )
    csv_file = tmp_path / "custom.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    custom_map: ColumnMap = {
        "booking_date": ["Datum"],
        "amount": ["Wert"],
        "currency": ["Waehrung"],
        "payee": ["Empfaenger"],
        "purpose": ["Info"],
    }

    session_factory = test_app._transport.app.state.session_factory  # type: ignore[attr-defined]
    async with session_factory() as session:
        result = await import_transactions_from_csv_path(
            session=session,
            account_id=account_id,
            csv_path=csv_file,
            column_map=custom_map,
        )

    assert result.created == 1, result
    assert result.failed == 0, result

    txn_resp = await test_app.get(
        "/api/transactions", params={"account_id": account_id}
    )
    items = txn_resp.json()["items"]
    assert len(items) == 1
    assert items[0]["payee"] == "Bäcker"
    assert items[0]["purpose"] == "Bread purchase"
    assert items[0]["amount"] == "-25.00"


@pytest.mark.asyncio
async def test_csv_import_account_not_found_raises(
    test_app: AsyncClient,
    tmp_path: Path,
) -> None:
    csv_file = tmp_path / "import.csv"
    csv_file.write_text(
        "booking_date,amount,currency\n2026-01-18,-1.00,EUR\n", encoding="utf-8"
    )

    session_factory = test_app._transport.app.state.session_factory  # type: ignore[attr-defined]
    async with session_factory() as session:
        with pytest.raises(NotFoundError, match="not found"):
            await import_transactions_from_csv_path(
                session=session,
                account_id=99999,
                csv_path=csv_file,
            )


@pytest.mark.asyncio
async def test_csv_import_dmy_invalid_date_counted_as_failed(
    test_app: AsyncClient,
    tmp_path: Path,
) -> None:
    acc = await create_account(test_app)

    csv_file = tmp_path / "import.csv"
    csv_file.write_text(
        "booking_date,amount,currency\nnot-a-date,-1.00,EUR\n", encoding="utf-8"
    )

    session_factory = test_app._transport.app.state.session_factory  # type: ignore[attr-defined]
    async with session_factory() as session:
        result = await import_transactions_from_csv_path(
            session=session,
            account_id=acc["id"],
            csv_path=csv_file,
            date_format="dmy",
        )

    assert result.total_rows == 1
    assert result.failed == 1
    assert result.created == 0
    assert len(result.errors) == 1


@pytest.mark.asyncio
async def test_csv_import_unsupported_date_format_counted_as_failed(
    test_app: AsyncClient,
    tmp_path: Path,
) -> None:
    acc = await create_account(test_app)

    csv_file = tmp_path / "import.csv"
    csv_file.write_text(
        "booking_date,amount,currency\n2026-01-18,-1.00,EUR\n", encoding="utf-8"
    )

    session_factory = test_app._transport.app.state.session_factory  # type: ignore[attr-defined]
    async with session_factory() as session:
        result = await import_transactions_from_csv_path(
            session=session,
            account_id=acc["id"],
            csv_path=csv_file,
            date_format="ymd_unsupported",
        )

    assert result.total_rows == 1
    assert result.failed == 1
    assert result.created == 0


@pytest.mark.asyncio
async def test_csv_import_cannot_decode_raises(
    test_app: AsyncClient,
    tmp_path: Path,
) -> None:
    """A file with bytes invalid in both utf-8-sig and cp1252 raises ValueError."""
    acc = await create_account(test_app)

    # Bytes 0x81 and 0x8D are undefined in cp1252 and invalid in utf-8
    csv_file = tmp_path / "bad_encoding.csv"
    csv_file.write_bytes(b"booking_date,amount,currency\n\x81\x8d,-1.00,EUR\n")

    session_factory = test_app._transport.app.state.session_factory  # type: ignore[attr-defined]
    async with session_factory() as session:
        with pytest.raises(CsvFormatError, match="Cannot decode"):
            await import_transactions_from_csv_path(
                session=session,
                account_id=acc["id"],
                csv_path=csv_file,
            )


@pytest.mark.asyncio
async def test_csv_import_cp1252_encoding_fallback(
    test_app: AsyncClient,
    tmp_path: Path,
) -> None:
    """A file encoded in cp1252 (not valid utf-8) is decoded via the fallback path."""
    acc = await create_account(test_app)

    # ü in cp1252 is 0xFC — invalid utf-8 continuation byte in this position
    csv_content = (
        "booking_date,amount,currency,payee\n2026-01-18,-5.00,EUR,Br\xfcckner\n"
    )
    csv_file = tmp_path / "cp1252.csv"
    csv_file.write_bytes(csv_content.encode("cp1252"))

    session_factory = test_app._transport.app.state.session_factory  # type: ignore[attr-defined]
    async with session_factory() as session:
        result = await import_transactions_from_csv_path(
            session=session,
            account_id=acc["id"],
            csv_path=csv_file,
        )

    assert result.created == 1
    assert result.failed == 0

    txn_resp = await test_app.get("/api/transactions", params={"account_id": acc["id"]})
    assert txn_resp.json()["items"][0]["payee"] == "Brückner"


@pytest.mark.asyncio
async def test_csv_import_no_header_row_raises(
    test_app: AsyncClient,
    tmp_path: Path,
) -> None:
    acc = await create_account(test_app)

    csv_file = tmp_path / "empty.csv"
    csv_file.write_text("", encoding="utf-8")

    session_factory = test_app._transport.app.state.session_factory  # type: ignore[attr-defined]
    async with session_factory() as session:
        with pytest.raises(CsvFormatError, match="no header"):
            await import_transactions_from_csv_path(
                session=session,
                account_id=acc["id"],
                csv_path=csv_file,
            )


@pytest.mark.asyncio
async def test_csv_import_missing_required_column_counted_as_failed(
    test_app: AsyncClient,
    tmp_path: Path,
) -> None:
    """A CSV whose columns don't match any known mapping triggers KeyError per row."""
    acc = await create_account(test_app)

    # Header exists but no recognised column names
    csv_file = tmp_path / "unknown_cols.csv"
    csv_file.write_text("foo,bar,baz\n1,2,3\n4,5,6\n", encoding="utf-8")

    session_factory = test_app._transport.app.state.session_factory  # type: ignore[attr-defined]
    async with session_factory() as session:
        result = await import_transactions_from_csv_path(
            session=session,
            account_id=acc["id"],
            csv_path=csv_file,
        )

    assert result.total_rows == 2
    assert result.failed == 2
    assert result.created == 0
    assert len(result.errors) == 2
    assert "Missing column" in result.errors[0].message


@pytest.mark.asyncio
async def test_csv_import_max_errors_cap(
    test_app: AsyncClient,
    tmp_path: Path,
) -> None:
    """errors list is capped at max_errors even when more rows fail."""
    acc = await create_account(test_app)

    rows = "\n".join(f"not-a-date,-{i}.00,EUR" for i in range(1, 12))
    csv_file = tmp_path / "many_bad.csv"
    csv_file.write_text(f"booking_date,amount,currency\n{rows}\n", encoding="utf-8")

    session_factory = test_app._transport.app.state.session_factory  # type: ignore[attr-defined]
    async with session_factory() as session:
        result = await import_transactions_from_csv_path(
            session=session,
            account_id=acc["id"],
            csv_path=csv_file,
            max_errors=5,
        )

    assert result.failed == 11
    assert len(result.errors) == 5


@pytest.mark.asyncio
async def test_csv_import_applies_categorization_rule(
    test_app: AsyncClient,
    tmp_path: Path,
) -> None:
    """Transactions matching a rule get category_id set during import."""
    acc = await create_account(test_app)
    cat = await create_category(test_app, name="Groceries")
    await create_rule(
        test_app,
        field="payee",
        operator="contains",
        value="Rewe",
        category_id=cat["id"],
    )

    csv_file = tmp_path / "import.csv"
    csv_file.write_text(
        "booking_date,amount,currency,payee\n2026-01-18,-12.34,EUR,Rewe\n",
        encoding="utf-8",
    )

    session_factory = test_app._transport.app.state.session_factory  # type: ignore[attr-defined]
    async with session_factory() as session:
        result = await import_transactions_from_csv_path(
            session=session,
            account_id=acc["id"],
            csv_path=csv_file,
        )

    assert result.created == 1

    txn_resp = await test_app.get("/api/transactions", params={"account_id": acc["id"]})
    item = txn_resp.json()["items"][0]
    assert item["category_id"] == cat["id"]
