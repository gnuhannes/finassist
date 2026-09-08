from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest
from httpx import AsyncClient

from tests.helpers import create_account, create_category, create_transaction


def _sqlite_bytes(*, core_tables: bool, alembic_revision: str | None) -> bytes:
    """A syntactically valid SQLite file with tunable contents."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE placeholder (id INTEGER)")
    if core_tables:
        conn.execute("CREATE TABLE account (id INTEGER)")
        conn.execute('CREATE TABLE "transaction" (id INTEGER)')
        conn.execute("CREATE TABLE category (id INTEGER)")
    if alembic_revision is not None:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32))")
        conn.execute("INSERT INTO alembic_version VALUES (?)", (alembic_revision,))
    conn.commit()
    conn.close()
    data = Path(path).read_bytes()
    os.unlink(path)
    return data


@pytest.mark.asyncio
async def test_restore_rejects_sqlite_missing_core_tables(
    test_app: AsyncClient,
) -> None:
    body = _sqlite_bytes(core_tables=False, alembic_revision=None)
    resp = await test_app.post(
        "/api/restore/sqlite", files={"file": ("x.sqlite", body, "x")}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_restore_rejects_unknown_schema_revision(test_app: AsyncClient) -> None:
    body = _sqlite_bytes(core_tables=True, alembic_revision="zzz999notreal")
    resp = await test_app.post(
        "/api/restore/sqlite", files={"file": ("x.sqlite", body, "x")}
    )
    assert resp.status_code == 400
    assert "revision" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_restore_rejects_corrupt_file(test_app: AsyncClient) -> None:
    corrupt = b"SQLite format 3\x00" + b"\x00" * 400
    resp = await test_app.post(
        "/api/restore/sqlite",
        files={"file": ("x.sqlite", corrupt, "x")},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_restore_rejects_non_sqlite(test_app: AsyncClient) -> None:
    resp = await test_app.post(
        "/api/restore/sqlite",
        files={
            "file": (
                "bad.sqlite",
                b"this is not a sqlite file",
                "application/octet-stream",
            )
        },
    )
    assert resp.status_code == 400
    assert "valid SQLite" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_restore_sqlite_replaces_data(test_app: AsyncClient) -> None:
    # Seed an account before backup
    await create_account(test_app, name="OriginalAccount")

    # Export the current DB
    backup_resp = await test_app.get("/api/export/sqlite")
    assert backup_resp.status_code == 200
    backup_bytes = backup_resp.content

    # Delete the original account and add a new one
    await create_account(test_app, name="NewAccount")
    accs_before = (await test_app.get("/api/accounts")).json()
    names_before = {a["name"] for a in accs_before}
    assert "OriginalAccount" in names_before
    assert "NewAccount" in names_before

    # Restore the backup (which only has OriginalAccount)
    restore_resp = await test_app.post(
        "/api/restore/sqlite",
        files={"file": ("backup.sqlite", backup_bytes, "application/octet-stream")},
    )
    assert restore_resp.status_code == 200
    assert restore_resp.json()["ok"] is True

    # After restore, only OriginalAccount should exist
    accs_after = (await test_app.get("/api/accounts")).json()
    names_after = {a["name"] for a in accs_after}
    assert "OriginalAccount" in names_after
    assert "NewAccount" not in names_after


@pytest.mark.asyncio
async def test_delete_transactions_keeps_accounts_and_categories(
    test_app: AsyncClient,
) -> None:
    acc = await create_account(test_app)
    await create_category(test_app, name="Food")
    await create_transaction(test_app, account_id=acc["id"])
    await create_transaction(
        test_app, account_id=acc["id"], amount="5.00", external_id="abc-2"
    )

    resp = await test_app.delete("/api/data/transactions")
    assert resp.status_code == 200
    assert resp.json()["deleted"] >= 2

    # Transactions gone
    txns = (
        await test_app.get("/api/transactions", params={"account_id": acc["id"]})
    ).json()
    assert txns["items"] == []

    # Accounts and categories intact
    accs = (await test_app.get("/api/accounts")).json()
    assert any(a["id"] == acc["id"] for a in accs)

    cats = (await test_app.get("/api/categories")).json()
    assert any(c["name"] == "Food" for c in cats)


@pytest.mark.asyncio
async def test_wipe_all_data(test_app: AsyncClient) -> None:
    acc = await create_account(test_app)
    await create_category(test_app, name="Travel")
    await create_transaction(test_app, account_id=acc["id"])

    resp = await test_app.delete("/api/data")
    assert resp.status_code == 200
    assert resp.json()["deleted"] >= 3

    assert (await test_app.get("/api/accounts")).json() == []
    assert (await test_app.get("/api/categories")).json() == []
    txns = (
        await test_app.get("/api/transactions", params={"account_id": acc["id"]})
    ).json()
    assert txns["items"] == []
