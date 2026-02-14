"""
uca_orchestrator.api.routers.internal.systems.registration

Dummy registration system.

Responsibilities:
- Provide the authoritative submission payload for a use case.
- Emulate an upstream registration service.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_404_NOT_FOUND

from uca_orchestrator.api.deps import db_session
from uca_orchestrator.auth.deps import require_roles
from uca_orchestrator.db.repositories.use_cases import UseCaseRepo

router = APIRouter()


class RegistrationStatusResponse(BaseModel):
    external_use_case_id: str | None
    owner: str
    submission_payload: dict[str, Any]


@router.get(
    "/{use_case_id}/status",
    response_model=RegistrationStatusResponse,
    dependencies=[Depends(require_roles("internal_system"))],
)
async def get_registration_status(
    use_case_id: uuid.UUID,
    session: AsyncSession = Depends(db_session),
) -> RegistrationStatusResponse:
    # Internal auth is enforced via dependency: role=internal_system.
    uc = await UseCaseRepo(session).get(use_case_id)
    if uc is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Use case not found")
    return RegistrationStatusResponse(
        external_use_case_id=uc.external_use_case_id,
        owner=uc.owner,
        submission_payload=uc.submission_payload,
    )


class RegistrationUpdateRequest(BaseModel):
    external_use_case_id: str = Field(min_length=1, max_length=128)


@router.post(
    "/{use_case_id}/link-external",
    dependencies=[Depends(require_roles("internal_system"))],
)
async def link_external_use_case_id(
    use_case_id: uuid.UUID,
    body: RegistrationUpdateRequest,
    session: AsyncSession = Depends(db_session),
) -> dict[str, str]:
    # This endpoint simulates linking an internal use-case to an upstream registration id.
    uc = await UseCaseRepo(session).get(use_case_id)
    if uc is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Use case not found")
    uc.external_use_case_id = body.external_use_case_id
    await session.commit()
    return {"status": "ok"}


# --- Module Notes -----------------------------------------------------------
# Registration status is called by `parallel_fetch_node` via InternalApiClient.
