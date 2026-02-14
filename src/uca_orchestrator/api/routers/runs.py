from __future__ import annotations

import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_404_NOT_FOUND

from uca_orchestrator.api.deps import db_session, settings_dep
from uca_orchestrator.auth.deps import get_principal, require_roles
from uca_orchestrator.auth.models import Principal
from uca_orchestrator.db.repositories.runs import RunRepo
from uca_orchestrator.services.orchestration_service import OrchestrationService
from uca_orchestrator.settings import Settings

router = APIRouter(prefix="/v1/runs", tags=["runs"])


class ResumeRequest(BaseModel):
    decision: dict[str, Any] = Field(default_factory=dict)


@router.post(
    "/{run_id}/resume",
    dependencies=[Depends(require_roles("governance_reviewer"))],
)
async def resume_run(
    request: Request,
    run_id: uuid.UUID,
    body: ResumeRequest,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(db_session),
    settings: Settings = Depends(settings_dep),
) -> dict[str, Any]:
    run = await RunRepo(session).get(run_id)
    if run is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Run not found")

    transport = httpx.ASGITransport(app=request.app)
    async with httpx.AsyncClient(
        transport=transport, base_url=str(request.base_url).rstrip("/")
    ) as http:
        svc = OrchestrationService(session=session, settings=settings, http=http)
        return await svc.resume(run_id=run_id, actor=principal.subject, decision=body.decision)
