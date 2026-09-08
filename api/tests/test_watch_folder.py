from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from my_private_finances.db import create_engine, create_session_factory
from my_private_finances.services.watch_folder import (
    _move_to_failed,
    _move_to_processed,
    _process_file,
    watch_folder_task,
)
from tests.helpers import create_account

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


async def _create_csv_profile(test_app: AsyncClient) -> dict:
    resp = await test_app.post(
        "/api/csv-profiles",
        json={
            "name": "test-profile",
            "delimiter": ",",
            "date_format": "iso",
            "decimal_comma": False,
        },
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Settings endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_watch_settings_default(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/watch-folder/settings")
    assert resp.status_code == 200
    assert resp.json()["root_path"] == "data/watch"


@pytest.mark.asyncio
async def test_patch_watch_settings(test_app: AsyncClient) -> None:
    async def _noop(*args: object, **kwargs: object) -> None:
        pass

    with patch(
        "my_private_finances.api.routes.watch_folder.watch_folder_task",
        side_effect=_noop,
    ):
        # Seed an old watcher task so the route has something to cancel
        old_task = asyncio.create_task(asyncio.sleep(100))
        test_app._transport.app.state.watcher_task = old_task  # type: ignore[union-attr]

        resp = await test_app.patch(
            "/api/watch-folder/settings", json={"root_path": "/tmp/my-watch"}
        )
        assert resp.status_code == 200
        assert resp.json()["root_path"] == "/tmp/my-watch"


# ---------------------------------------------------------------------------
# Config CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_configs_empty(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/watch-folder/configs")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_and_list_config(test_app: AsyncClient) -> None:
    account = await create_account(test_app)
    resp = await test_app.post(
        "/api/watch-folder/configs",
        json={"subfolder_name": "dkb-checking", "account_id": account["id"]},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["subfolder_name"] == "dkb-checking"
    assert body["account_id"] == account["id"]
    assert body["profile_id"] is None

    list_resp = await test_app.get("/api/watch-folder/configs")
    assert len(list_resp.json()) == 1


@pytest.mark.asyncio
async def test_create_config_duplicate_subfolder_returns_409(
    test_app: AsyncClient,
) -> None:
    account = await create_account(test_app)
    await test_app.post(
        "/api/watch-folder/configs",
        json={"subfolder_name": "savings", "account_id": account["id"]},
    )
    resp = await test_app.post(
        "/api/watch-folder/configs",
        json={"subfolder_name": "savings", "account_id": account["id"]},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_update_config(test_app: AsyncClient) -> None:
    account = await create_account(test_app)
    profile = await _create_csv_profile(test_app)

    create_resp = await test_app.post(
        "/api/watch-folder/configs",
        json={"subfolder_name": "checking", "account_id": account["id"]},
    )
    config_id = create_resp.json()["id"]

    resp = await test_app.put(
        f"/api/watch-folder/configs/{config_id}",
        json={"profile_id": profile["id"]},
    )
    assert resp.status_code == 200
    assert resp.json()["profile_id"] == profile["id"]


@pytest.mark.asyncio
async def test_delete_config(test_app: AsyncClient) -> None:
    account = await create_account(test_app)
    create_resp = await test_app.post(
        "/api/watch-folder/configs",
        json={"subfolder_name": "to-delete", "account_id": account["id"]},
    )
    config_id = create_resp.json()["id"]

    resp = await test_app.delete(f"/api/watch-folder/configs/{config_id}")
    assert resp.status_code == 204

    list_resp = await test_app.get("/api/watch-folder/configs")
    assert list_resp.json() == []


@pytest.mark.asyncio
async def test_delete_config_not_found(test_app: AsyncClient) -> None:
    resp = await test_app.delete("/api/watch-folder/configs/9999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# File move utilities
# ---------------------------------------------------------------------------


def test_move_to_processed(tmp_path: Path) -> None:
    src = tmp_path / "statement.csv"
    src.write_text("content")
    processed_dir = tmp_path / "processed" / "2026-03-04"

    _move_to_processed(src, processed_dir)

    assert not src.exists()
    assert (processed_dir / "statement.csv").exists()


def test_move_to_processed_collision(tmp_path: Path) -> None:
    src = tmp_path / "statement.csv"
    src.write_text("new content")
    processed_dir = tmp_path / "processed" / "2026-03-04"
    processed_dir.mkdir(parents=True)
    (processed_dir / "statement.csv").write_text("existing")

    _move_to_processed(src, processed_dir)

    assert (processed_dir / "statement_1.csv").exists()


def test_move_to_failed(tmp_path: Path) -> None:
    src = tmp_path / "broken.csv"
    src.write_text("bad content")
    failed_dir = tmp_path / "failed"

    _move_to_failed(src, failed_dir, "Something went wrong")

    assert not src.exists()
    assert (failed_dir / "broken.csv").exists()
    assert (failed_dir / "broken.csv.error.txt").read_text() == "Something went wrong"


# ---------------------------------------------------------------------------
# _process_file service tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_file_no_config_moves_to_failed(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    """A file in a subfolder with no config lands in failed/."""
    watch_root = tmp_path / "watch"
    subfolder = watch_root / "unconfigured-folder"
    subfolder.mkdir(parents=True)
    src = subfolder / "statement.csv"
    src.write_text("col1,col2\n1,2")

    session_factory = test_app._transport.app.state.session_factory  # type: ignore[union-attr]
    await _process_file(src, session_factory)

    assert not src.exists()
    failed = tmp_path / "failed" / "statement.csv"
    assert failed.exists()
    assert "No watch folder config" in failed.with_suffix(".csv.error.txt").read_text()


@pytest.mark.asyncio
async def test_process_file_csv_with_valid_config(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    """A CSV file in a configured subfolder is imported and moved to processed/."""
    account = await create_account(test_app)
    create_resp = await test_app.post(
        "/api/watch-folder/configs",
        json={"subfolder_name": "checking", "account_id": account["id"]},
    )
    assert create_resp.status_code == 201

    watch_root = tmp_path / "watch"
    subfolder = watch_root / "checking"
    subfolder.mkdir(parents=True)
    src = subfolder / "statement.csv"
    src.write_text(
        "booking_date,amount,currency,payee,purpose\n"
        "2026-01-01,10.00,EUR,REWE,Groceries\n"
    )

    session_factory = test_app._transport.app.state.session_factory  # type: ignore[union-attr]
    await _process_file(src, session_factory)

    assert not src.exists()
    processed = list((tmp_path / "processed").rglob("*.csv"))
    assert len(processed) == 1


@pytest.mark.asyncio
async def test_process_file_import_exception_moves_to_failed(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    """An import exception causes the file to land in failed/ with an error file."""
    account = await create_account(test_app)
    await test_app.post(
        "/api/watch-folder/configs",
        json={"subfolder_name": "erroring", "account_id": account["id"]},
    )

    watch_root = tmp_path / "watch"
    subfolder = watch_root / "erroring"
    subfolder.mkdir(parents=True)
    src = subfolder / "bad.csv"
    src.write_text("booking_date,amount,currency\n2026-01-01,10.00,EUR")

    session_factory = test_app._transport.app.state.session_factory  # type: ignore[union-attr]

    with patch(
        "my_private_finances.services.watch_folder.import_transactions_from_csv_path",
        side_effect=ValueError("simulated import failure"),
    ):
        await _process_file(src, session_factory)

    assert not src.exists()
    failed = tmp_path / "failed" / "bad.csv"
    assert failed.exists()
    assert (
        "simulated import failure" in failed.with_suffix(".csv.error.txt").read_text()
    )


# ---------------------------------------------------------------------------
# watch_folder_task lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_watch_folder_task_creates_directory_and_cancels_cleanly(
    tmp_path: Path,
) -> None:
    """watch_folder_task creates the watch dir and stops cleanly on cancellation."""
    from sqlmodel import SQLModel

    watch_path = tmp_path / "watch"
    db_path = tmp_path / "wf.sqlite"
    engine = create_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    factory = create_session_factory(engine)

    async with engine.connect() as conn:
        async with conn.begin():
            await conn.run_sync(SQLModel.metadata.create_all)

    task = asyncio.create_task(watch_folder_task(factory, watch_path))
    await asyncio.sleep(0.05)  # let the task start

    assert watch_path.exists()

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass  # expected

    await engine.dispose()
