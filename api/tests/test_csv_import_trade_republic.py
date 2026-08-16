from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient

from my_private_finances.services.csv_import import (
    ColumnMap,
    import_transactions_from_csv_path,
)
from tests.helpers import create_account

TR_COLUMN_MAP: ColumnMap = {
    "booking_date": ["date"],
    "amount": ["amount"],
    "currency": ["currency"],
    "payee": ["name", "counterparty_name"],
    "purpose": ["type"],
    "external_id": ["transaction_id"],
    "notes": [],
}
TR_ROW_FILTERS = {"category": ["CASH"]}
TR_ROW_EXCLUDE_FILTERS = {"type": ["PRIVATE_MARKET_BUY"]}

# Minimal TR CSV with 3 importable CASH rows, 2 TRADING rows, 1 PRIVATE_MARKET_BUY row.
# Columns: datetime,date,account_type,category,type,asset_class,name,symbol,shares,price,
#          amount,fee,tax,currency,original_amount,original_currency,fx_rate,description,
#          transaction_id,counterparty_name,counterparty_iban,payment_reference,mcc_code
_TR_HEADER = (
    "datetime,date,account_type,category,type,asset_class,name,symbol,shares,price,"
    "amount,fee,tax,currency,original_amount,original_currency,fx_rate,description,"
    "transaction_id,counterparty_name,counterparty_iban,payment_reference,mcc_code"
)
TR_CSV = (
    "\n".join(
        [
            _TR_HEADER,
            # CASH / CARD_TRANSACTION — should be imported
            "2025-09-01T09:39:13.160169Z,2025-09-01,DEFAULT,CASH,CARD_TRANSACTION,,Brown-Block,,,,-5845.30,,,EUR,,,,NUnTTzvZrwjz,7454237a-8e0f-3a53-8680-a09f2dd1ec44,,,,9646",
            # CASH / TRANSFER_INBOUND — should be imported
            "2025-09-01T13:39:12.746341Z,2025-09-01,DEFAULT,CASH,TRANSFER_INBOUND,,,,,,7661,,,EUR,,,,dXkfdKltutcz,ea277ee8-acb7-3078-ace1-0761bdff0605,,,,",
            # CASH / INTEREST_PAYMENT — should be imported
            "2025-08-01T07:30:20.246670Z,2025-08-01,DEFAULT,CASH,INTEREST_PAYMENT,,,,,,9548.12,,-8773.57,EUR,,,,OJceIgENJbPZ,f54ab916-1b3d-3bac-ac26-cb8c542e1c04,,,,",
            # TRADING / BUY — should be skipped (row_filters)
            "2025-09-02T14:51:13.114Z,2025-09-02,DEFAULT,TRADING,BUY,FUND,Trantow and Sons,hhHqvYUrvDPl,8815.04,4230.06,-7747.36,,,EUR,,,,RIybuEmPFTiR,1939b178-f5fc-3a8f-a55a-f6f7b69d16f8,,,,",
            # TRADING / BUY — should be skipped (row_filters)
            "2025-09-02T14:52:55.170Z,2025-09-02,DEFAULT,TRADING,BUY,FUND,Trantow and Sons,hhHqvYUrvDPl,5053.14,449.13,-1024,,,EUR,,,,AClBOllpGZRv,3be20ab3-84e4-3e49-a282-eb07ef89f22c,,,,",
            # CASH / PRIVATE_MARKET_BUY — should be skipped (row_exclude_filters)
            "2025-09-23T14:50:21.150582Z,2025-09-23,DEFAULT,CASH,PRIVATE_MARKET_BUY,PRIVATE_FUND,Smith-Kerluke,PcCVraoppQDu,,,-3381,,,EUR,,,,tZggoQFolYJY,5d0a5af8-5f63-349a-b80b-9127f86489a6,,,,",
        ]
    )
    + "\n"
)


@pytest.mark.asyncio
async def test_tr_cash_rows_imported(
    test_app: AsyncClient,
    tmp_path: Path,
) -> None:
    acc = await create_account(test_app)
    csv_file = tmp_path / "tr.csv"
    csv_file.write_text(TR_CSV, encoding="utf-8")

    session_factory = test_app._transport.app.state.session_factory  # type: ignore[attr-defined]
    async with session_factory() as session:  # type: ignore[call-arg]
        res = await import_transactions_from_csv_path(
            session=session,
            account_id=acc["id"],
            csv_path=csv_file,
            column_map=TR_COLUMN_MAP,
            row_filters=TR_ROW_FILTERS,
            row_exclude_filters=TR_ROW_EXCLUDE_FILTERS,
        )

    assert res.total_rows == 6, f"Expected 6 total rows, got {res}"
    assert res.created == 3, f"Expected 3 created (3 cash rows), got {res}"
    assert res.skipped == 3, (
        f"Expected 3 skipped (2 TRADING + 1 PRIVATE_MARKET_BUY), got {res}"
    )
    assert res.duplicates == 0, f"Expected 0 duplicates, got {res}"
    assert res.failed == 0, f"Expected 0 failed, got {res}"


@pytest.mark.asyncio
async def test_tr_trading_rows_skipped(
    test_app: AsyncClient,
    tmp_path: Path,
) -> None:
    acc = await create_account(test_app)
    csv_content = (
        "\n".join(
            [
                _TR_HEADER,
                "2025-09-02T14:51:13.114Z,2025-09-02,DEFAULT,TRADING,BUY,FUND,Trantow and Sons,hhHqvYUrvDPl,8815.04,4230.06,-7747.36,,,EUR,,,,RIybuEmPFTiR,1939b178-f5fc-3a8f-a55a-f6f7b69d16f8,,,,",
            ]
        )
        + "\n"
    )
    csv_file = tmp_path / "tr_trading.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    session_factory = test_app._transport.app.state.session_factory  # type: ignore[attr-defined]
    async with session_factory() as session:  # type: ignore[call-arg]
        res = await import_transactions_from_csv_path(
            session=session,
            account_id=acc["id"],
            csv_path=csv_file,
            column_map=TR_COLUMN_MAP,
            row_filters=TR_ROW_FILTERS,
        )

    assert res.total_rows == 1
    assert res.skipped == 1, f"TRADING row should be skipped, got {res}"
    assert res.created == 0
    assert res.failed == 0


@pytest.mark.asyncio
async def test_tr_private_market_buy_skipped(
    test_app: AsyncClient,
    tmp_path: Path,
) -> None:
    acc = await create_account(test_app)
    csv_content = (
        "\n".join(
            [
                _TR_HEADER,
                "2025-09-23T14:50:21.150582Z,2025-09-23,DEFAULT,CASH,PRIVATE_MARKET_BUY,PRIVATE_FUND,Smith-Kerluke,PcCVraoppQDu,,,-3381,,,EUR,,,,tZggoQFolYJY,5d0a5af8-5f63-349a-b80b-9127f86489a6,,,,",
            ]
        )
        + "\n"
    )
    csv_file = tmp_path / "tr_pmb.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    session_factory = test_app._transport.app.state.session_factory  # type: ignore[attr-defined]
    async with session_factory() as session:  # type: ignore[call-arg]
        res = await import_transactions_from_csv_path(
            session=session,
            account_id=acc["id"],
            csv_path=csv_file,
            column_map=TR_COLUMN_MAP,
            row_filters=TR_ROW_FILTERS,
            row_exclude_filters=TR_ROW_EXCLUDE_FILTERS,
        )

    assert res.total_rows == 1
    assert res.skipped == 1, f"PRIVATE_MARKET_BUY row should be skipped, got {res}"
    assert res.created == 0
    assert res.failed == 0


@pytest.mark.asyncio
async def test_tr_column_mapping(
    test_app: AsyncClient,
    tmp_path: Path,
) -> None:
    acc = await create_account(test_app)
    csv_content = (
        "\n".join(
            [
                _TR_HEADER,
                "2025-09-01T09:39:13.160169Z,2025-09-01,DEFAULT,CASH,CARD_TRANSACTION,,Brown-Block,,,,-5845.30,,,EUR,,,,NUnTTzvZrwjz,7454237a-8e0f-3a53-8680-a09f2dd1ec44,,,,9646",
            ]
        )
        + "\n"
    )
    csv_file = tmp_path / "tr_map.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    session_factory = test_app._transport.app.state.session_factory  # type: ignore[attr-defined]
    async with session_factory() as session:  # type: ignore[call-arg]
        res = await import_transactions_from_csv_path(
            session=session,
            account_id=acc["id"],
            csv_path=csv_file,
            column_map=TR_COLUMN_MAP,
            row_filters=TR_ROW_FILTERS,
        )

    assert res.created == 1, f"Expected 1 created, got {res}"

    resp = await test_app.get("/api/transactions", params={"account_id": acc["id"]})
    assert resp.status_code == 200
    rows = resp.json()["items"]
    assert len(rows) == 1
    tx = rows[0]

    assert tx["booking_date"] == "2025-09-01", (
        f"date column should map to booking_date: {tx}"
    )
    assert tx["amount"] == "-5845.30", f"amount: {tx}"
    assert tx["currency"] == "EUR", f"currency: {tx}"
    assert tx["payee"] == "Brown-Block", f"name should map to payee: {tx}"
    assert tx["purpose"] == "CARD_TRANSACTION", f"type should map to purpose: {tx}"
    assert tx["external_id"] == "7454237a-8e0f-3a53-8680-a09f2dd1ec44", (
        f"transaction_id should map to external_id: {tx}"
    )


@pytest.mark.asyncio
async def test_tr_missing_amount_silently_skipped(
    test_app: AsyncClient,
    tmp_path: Path,
) -> None:
    """A row whose amount cell is empty (column present) is silently skipped, not an error."""
    acc = await create_account(test_app)
    csv_content = (
        "\n".join(
            [
                _TR_HEADER,
                # Valid CASH row
                "2025-09-01T09:39:13.160169Z,2025-09-01,DEFAULT,CASH,CARD_TRANSACTION,,Brown-Block,,,,-5845.30,,,EUR,,,,NUnTTzvZrwjz,7454237a-8e0f-3a53-8680-a09f2dd1ec44,,,,9646",
                # Informational row — amount column present but empty
                "2025-09-01T10:00:00.000000Z,2025-09-01,DEFAULT,CASH,INFO,,,,,,,,,,,,,,info-row-id,,,,",
            ]
        )
        + "\n"
    )
    csv_file = tmp_path / "tr_missing_amount.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    session_factory = test_app._transport.app.state.session_factory  # type: ignore[attr-defined]
    async with session_factory() as session:  # type: ignore[call-arg]
        res = await import_transactions_from_csv_path(
            session=session,
            account_id=acc["id"],
            csv_path=csv_file,
            column_map=TR_COLUMN_MAP,
            row_filters=TR_ROW_FILTERS,
        )

    assert res.total_rows == 2
    assert res.created == 1, f"Only the valid cash row should be created, got {res}"
    assert res.skipped == 1, f"Empty-amount row should be silently skipped, got {res}"
    assert res.failed == 0, f"Empty-amount row must not be an error, got {res}"


@pytest.mark.asyncio
async def test_tr_idempotent(
    test_app: AsyncClient,
    tmp_path: Path,
) -> None:
    acc = await create_account(test_app)
    csv_file = tmp_path / "tr_idempotent.csv"
    csv_file.write_text(TR_CSV, encoding="utf-8")

    session_factory = test_app._transport.app.state.session_factory  # type: ignore[attr-defined]

    async with session_factory() as session:  # type: ignore[call-arg]
        res1 = await import_transactions_from_csv_path(
            session=session,
            account_id=acc["id"],
            csv_path=csv_file,
            column_map=TR_COLUMN_MAP,
            row_filters=TR_ROW_FILTERS,
            row_exclude_filters=TR_ROW_EXCLUDE_FILTERS,
        )
    assert res1.created == 3

    async with session_factory() as session:  # type: ignore[call-arg]
        res2 = await import_transactions_from_csv_path(
            session=session,
            account_id=acc["id"],
            csv_path=csv_file,
            column_map=TR_COLUMN_MAP,
            row_filters=TR_ROW_FILTERS,
            row_exclude_filters=TR_ROW_EXCLUDE_FILTERS,
        )

    assert res2.total_rows == 6
    assert res2.created == 0, f"Re-import should create nothing, got {res2}"
    assert res2.skipped == 3, f"Filtered rows should still be skipped, got {res2}"
    assert res2.duplicates == 3, (
        f"Previously imported rows should be duplicates, got {res2}"
    )
    assert res2.failed == 0
