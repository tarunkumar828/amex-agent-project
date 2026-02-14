from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from uca_orchestrator.api.deps import db_session
from uca_orchestrator.auth.deps import require_roles
from uca_orchestrator.db.repositories.artifacts import ArtifactRepo

router = APIRouter(dependencies=[Depends(require_roles("internal_system"))])


class ArtifactStatusResponse(BaseModel):
    artifact_types: list[str] = Field(default_factory=list)


@router.get("/{use_case_id}/status", response_model=ArtifactStatusResponse)
async def artifact_status(
    use_case_id: uuid.UUID,
    session: AsyncSession = Depends(db_session),
) -> ArtifactStatusResponse:
    artifacts = await ArtifactRepo(session).list_for_use_case(use_case_id)
    return ArtifactStatusResponse(artifact_types=[a.type.value for a in artifacts])
