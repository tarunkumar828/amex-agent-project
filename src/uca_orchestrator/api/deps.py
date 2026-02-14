from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from uca_orchestrator.settings import Settings, get_settings


def settings_dep() -> Settings:
    return get_settings()


def sessionmaker_from_app(request: Request) -> async_sessionmaker[AsyncSession]:
    return request.app.state.sessionmaker  # type: ignore[attr-defined]


async def db_session(
    session_factory: async_sessionmaker[AsyncSession] = Depends(sessionmaker_from_app),
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
