"""
uca_orchestrator.db.session

Async SQLAlchemy engine + session factory helpers.

Responsibilities:
- Create the async engine from settings.
- Create the async sessionmaker with safe defaults.
- Provide a session scope helper for non-FastAPI contexts.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from uca_orchestrator.settings import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    # pool_pre_ping helps detect stale connections in long-lived processes.
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        future=True,
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False avoids surprising lazy loads after commits.
    return async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )


async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """
    Explicit session scope for service-layer orchestration.
    In the API layer we'll typically manage this via FastAPI dependencies.
    """

    async with session_factory() as session:
        yield session


# --- Module Notes -----------------------------------------------------------
# The API layer uses FastAPI dependencies for session scoping (`api.deps.db_session`).
