"""/health endpoint + destructive-endpoint confirmation guard (#114, #99)."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import SQLModel

from my_private_finances.config import Settings
from my_private_finances.main import create_app
from my_private_finances.services.watch_folder import (
    WatcherStatus,
    watch_folder_supervisor,
)


@pytest.mark.asyncio
async def test_health_reports_watcher_status(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert set(body["watcher"]) == {
        "running",
        "last_error",
        "restarts",
        "files_processed",
        "root_path",
    }


@pytest.mark.asyncio
async def test_destructive_endpoints_require_guard_header() -> None:
    """A request without X-Requested-With is rejected with 403."""
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(
            data_dir=Path(tmp),
            database_url=f"sqlite+aiosqlite:///{Path(tmp) / 'g.sqlite'}",
        )
        app = create_app(settings)
        engine = app.state.engine
        async with engine.connect() as conn:
            async with conn.begin():
                await conn.run_sync(SQLModel.metadata.create_all)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as bare:
            for method, path in [
                ("DELETE", "/api/data"),
                ("DELETE", "/api/data/transactions"),
            ]:
                r = await bare.request(method, path)
                assert r.status_code == 403, (method, path, r.text)

            guarded = await bare.request(
                "DELETE", "/api/data", headers={"X-Requested-With": "1"}
            )
            assert guarded.status_code == 200
        await engine.dispose()


@pytest.mark.asyncio
async def test_supervisor_relaunches_after_crash() -> None:
    status = WatcherStatus()
    calls = 0

    async def flaky(_sf: object, _path: Path, st: WatcherStatus) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")
        st.running = True
        await asyncio.sleep(3600)

    import my_private_finances.services.watch_folder as wf

    orig = wf.watch_folder_task
    wf.watch_folder_task = flaky  # type: ignore[assignment]
    try:
        task = asyncio.create_task(
            watch_folder_supervisor(object(), Path("/tmp/x"), status, max_backoff=0.01)  # type: ignore[arg-type]
        )
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        wf.watch_folder_task = orig  # type: ignore[assignment]

    assert calls >= 2
    assert status.restarts >= 1
    assert status.last_error is not None and "boom" in status.last_error
