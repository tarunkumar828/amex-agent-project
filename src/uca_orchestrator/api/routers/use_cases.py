"""
uca_orchestrator.api.routers.use_cases

External/public endpoints for use case owners.

Responsibilities:
- Register a use case (persist submission payload).
- Start orchestration (execute LangGraph) and return status.
- Provide read APIs for audit trail and artifacts.
"""

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
from uca_orchestrator.db.repositories.artifacts import ArtifactRepo
from uca_orchestrator.db.repositories.audit import AuditRepo
from uca_orchestrator.db.repositories.runs import RunRepo
from uca_orchestrator.db.repositories.use_cases import UseCaseRepo
from uca_orchestrator.services.orchestration_service import OrchestrationService
from uca_orchestrator.settings import Settings

router = APIRouter(prefix="/v1/use-cases", tags=["use-cases"])


class UseCaseRegisterRequest(BaseModel):
    submission_payload: dict[str, Any] = Field(default_factory=dict)
    external_use_case_id: str | None = Field(default=None, max_length=128)


class UseCaseRegisterResponse(BaseModel):
    use_case_id: uuid.UUID
    run_id: uuid.UUID


class UseCaseResponse(BaseModel):
    id: uuid.UUID
    owner: str
    status: str
    classification: dict[str, Any]
    risk_level: str
    missing_artifacts: list[str]
    approval_status: dict[str, Any]
    eval_metrics: dict[str, Any]


@router.post(
    "/register",
    response_model=UseCaseRegisterResponse,
    dependencies=[Depends(require_roles("use_case_owner"))],
)
async def register_use_case(
    request: Request,
    body: UseCaseRegisterRequest,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(db_session),
    settings: Settings = Depends(settings_dep),
) -> UseCaseRegisterResponse:
    # AuthZ is enforced via router dependencies: role=use_case_owner.
    use_cases = UseCaseRepo(session)
    uc = await use_cases.create(
        owner=principal.subject,
        submission_payload=body.submission_payload,
        external_use_case_id=body.external_use_case_id,
    )

    # Create initial run (execution is explicit via /orchestrate).
    # We use ASGITransport so "tool calls" can hit internal endpoints in-process (no real network).
    transport = httpx.ASGITransport(app=request.app)
    async with httpx.AsyncClient(
        transport=transport, base_url=str(request.base_url).rstrip("/")
    ) as http:
        svc = OrchestrationService(session=session, settings=settings, http=http)
        run_id = await svc.start(use_case_id=uc.id, actor=principal.subject)
        await AuditRepo(session).add(
            use_case_id=uc.id,
            run_id=run_id,
            actor=principal.subject,
            event_type="USE_CASE_REGISTERED",
            details={"external_use_case_id": body.external_use_case_id},
        )
        await session.commit()
        return UseCaseRegisterResponse(use_case_id=uc.id, run_id=run_id)


@router.get(
    "/{use_case_id}",
    response_model=UseCaseResponse,
    dependencies=[Depends(require_roles("use_case_owner"))],
)
async def get_use_case(
    use_case_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(db_session),
) -> UseCaseResponse:
    uc = await UseCaseRepo(session).get(use_case_id)
    if uc is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Use case not found")
    if uc.owner != principal.subject and not principal.is_admin:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Use case not found")
    return UseCaseResponse(
        id=uc.id,
        owner=uc.owner,
        status=uc.status.value,
        classification=uc.classification or {},
        risk_level=uc.risk_level,
        missing_artifacts=uc.missing_artifacts or [],
        approval_status=uc.approval_status or {},
        eval_metrics=uc.eval_metrics or {},
    )


@router.post(
    "/{use_case_id}/orchestrate",
    dependencies=[Depends(require_roles("use_case_owner"))],
)
async def orchestrate_use_case(
    request: Request,
    use_case_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(db_session),
    settings: Settings = Depends(settings_dep),
) -> dict[str, Any]:
    uc = await UseCaseRepo(session).get(use_case_id)
    if uc is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Use case not found")
    if uc.owner != principal.subject and not principal.is_admin:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Use case not found")

    # Use ASGITransport to make real HTTP calls to internal endpoints (JWT-protected) without network.
    transport = httpx.ASGITransport(app=request.app)
    async with httpx.AsyncClient(
        transport=transport, base_url=str(request.base_url).rstrip("/")
    ) as http:
        svc = OrchestrationService(session=session, settings=settings, http=http)
        latest = await RunRepo(session).latest_for_use_case(use_case_id)
        run_id = (
            latest.id
            if latest is not None
            else await svc.start(use_case_id=use_case_id, actor=principal.subject)
        )
        return await svc.execute(run_id=run_id, actor=principal.subject)


@router.get(
    "/{use_case_id}/audit",
    dependencies=[Depends(require_roles("use_case_owner"))],
)
async def list_audit_events(
    use_case_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(db_session),
) -> list[dict[str, Any]]:
    # Audit is returned newest-first (see AuditRepo); clients can reverse if desired.
    uc = await UseCaseRepo(session).get(use_case_id)
    if uc is None or (uc.owner != principal.subject and not principal.is_admin):
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Use case not found")
    events = await AuditRepo(session).list_for_use_case(use_case_id)
    return [
        {
            "id": str(e.id),
            "event_type": e.event_type,
            "actor": e.actor,
            "details": e.details,
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]


@router.get(
    "/{use_case_id}/artifacts",
    dependencies=[Depends(require_roles("use_case_owner"))],
)
async def list_artifacts(
    use_case_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(db_session),
) -> list[dict[str, Any]]:
    uc = await UseCaseRepo(session).get(use_case_id)
    if uc is None or (uc.owner != principal.subject and not principal.is_admin):
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Use case not found")
    artifacts = await ArtifactRepo(session).list_for_use_case(use_case_id)
    return [
        {
            "id": str(a.id),
            "type": a.type.value,
            "content_type": a.content_type,
            "content": a.content,
            "created_at": a.created_at.isoformat(),
        }
        for a in artifacts
    ]


# --- Module Notes -----------------------------------------------------------
# This router intentionally does not embed orchestration logic; it delegates to
# OrchestrationService and returns a compact response.
