"""
uca_orchestrator.api.deps

FastAPI dependency wiring for the API layer.

Responsibilities:
- Provide dependency functions for settings and DB sessions.
- Encapsulate app.state access patterns (engine/sessionmaker).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from uca_orchestrator.settings import Settings, get_settings


def settings_dep() -> Settings:
    return get_settings()


def sessionmaker_from_app(request: Request) -> async_sessionmaker[AsyncSession]:
    # The sessionmaker is created on app startup in `uca_orchestrator.api.app.create_app`.
    return request.app.state.sessionmaker  # type: ignore[attr-defined]


async def db_session(
    session_factory: async_sessionmaker[AsyncSession] = Depends(sessionmaker_from_app),
) -> AsyncIterator[AsyncSession]:
    # Request-scoped DB session. Commit/rollback is managed explicitly by the service layer.
    async with session_factory() as session:
        yield session


# --- Module Notes -----------------------------------------------------------
# In larger systems, additional per-request resources (caches, tracing spans, etc.)
# are often injected via dependencies in this module.
