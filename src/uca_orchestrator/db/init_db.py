from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from uca_orchestrator.db.base import Base


async def init_db(engine: AsyncEngine) -> None:
    """
    Dev/test bootstrap: create tables if they don't exist.
    Production should rely on Alembic migrations (hooked up later).
    """

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
