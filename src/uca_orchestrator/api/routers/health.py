"""
uca_orchestrator.api.routers.health

Health and readiness endpoints.

Responsibilities:
- Provide liveness probe (`/healthz`).
- Provide readiness probe (`/readyz`) with DB connectivity validation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from uca_orchestrator.api.deps import db_session

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    # Liveness: process is up and serving HTTP.
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(session: AsyncSession = Depends(db_session)) -> dict[str, str]:
    # Readiness: verify critical dependency (DB) is reachable.
    await session.execute(text("SELECT 1"))
    return {"status": "ready"}


# --- Module Notes -----------------------------------------------------------
# Kubernetes typically uses /healthz for liveness and /readyz for readiness gating.
