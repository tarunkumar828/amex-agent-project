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


class HydraResponse(BaseModel):
    status: Literal["READY", "BLOCKED"]
    notes: str | None = None


@router.get("/{use_case_id}/readiness", response_model=HydraResponse)
async def hydra_readiness(
    use_case_id: uuid.UUID,
    session: AsyncSession = Depends(db_session),
) -> HydraResponse:
    uc = await UseCaseRepo(session).get(use_case_id)
    if uc is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Use case not found")

    # Dummy: blocked until approval-ready
    if uc.status.value == "APPROVAL_READY":
        return HydraResponse(status="READY", notes="Dummy deployment ready")
    return HydraResponse(status="BLOCKED", notes="Approval not complete")
