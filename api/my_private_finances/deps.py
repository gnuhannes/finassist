from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    sf: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with sf() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def require_confirmation(
    x_requested_with: Annotated[str | None, Header()] = None,
) -> None:
    """Guard for destructive / restore endpoints (SEC2).

    A cross-origin *simple* request can't set a custom header without a CORS
    preflight, which the origin allow-list rejects for unknown origins — so
    requiring ``X-Requested-With`` blocks a CSRF-shaped cross-site POST while
    staying a no-op for the SPA (its fetch wrapper always sends it).
    """
    if not x_requested_with:
        raise HTTPException(
            status_code=403,
            detail="This endpoint requires an 'X-Requested-With' header",
        )


RequireConfirmation = Depends(require_confirmation)
