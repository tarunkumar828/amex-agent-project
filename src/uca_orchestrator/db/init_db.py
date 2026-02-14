"""
uca_orchestrator.db.init_db

DB initialization helpers (dev/test convenience).

Responsibilities:
- Create tables for local development and tests.
- Keep production migration workflow separate (Alembic).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from uca_orchestrator.db.base import Base


async def init_db(engine: AsyncEngine) -> None:
    """
    Dev/test bootstrap: create tables if they don't exist.
    Production should rely on Alembic migrations (hooked up later).
    """

    # Use a transactional DDL block when supported by the backend.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# --- Module Notes -----------------------------------------------------------
# This helper is intentionally not used for prod. Production workflows should run
# Alembic migrations as part of deployment.
