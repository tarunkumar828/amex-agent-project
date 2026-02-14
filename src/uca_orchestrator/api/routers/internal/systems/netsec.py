"""
uca_orchestrator.api.routers.internal.systems.netsec

Dummy NetSec system.

Responsibilities:
- Provide a baseline security posture check derived from classification snapshot.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_404_NOT_FOUND

from uca_orchestrator.api.deps import db_session
from uca_orchestrator.auth.deps import require_roles
from uca_orchestrator.db.repositories.use_cases import UseCaseRepo

router = APIRouter(dependencies=[Depends(require_roles("internal_system"))])


class NetSecResponse(BaseModel):
    status: Literal["PASS", "FAIL", "PENDING"]
    notes: str | None = None


@router.get("/{use_case_id}/baseline", response_model=NetSecResponse)
async def netsec_baseline(
    use_case_id: uuid.UUID,
    session: AsyncSession = Depends(db_session),
) -> NetSecResponse:
    uc = await UseCaseRepo(session).get(use_case_id)
    if uc is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Use case not found")

    # Simple classification-derived decision; production systems would call scanners / policy engines.
    deployment = (uc.classification or {}).get("deployment_target", "UNKNOWN")
    if deployment == "CLOUD":
        return NetSecResponse(status="PASS", notes="Dummy cloud baseline satisfied")
    if deployment == "ON_PREM":
        return NetSecResponse(status="PASS", notes="Dummy on-prem baseline satisfied")
    return NetSecResponse(status="PENDING", notes="Missing deployment target")


# --- Module Notes -----------------------------------------------------------
# Exposed as a tool endpoint; orchestration can optionally incorporate this into approval logic.
