"""
uca_orchestrator.api.routers.internal.systems.artifacts

Artifact status tool endpoint (dummy system).

Responsibilities:
- Return the set of artifact types currently persisted for a use case.
- Enable orchestrator gap analysis (required vs present artifacts).
"""

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
    # This endpoint is intentionally lightweight; content retrieval is handled by public APIs.
    artifacts = await ArtifactRepo(session).list_for_use_case(use_case_id)
    return ArtifactStatusResponse(artifact_types=[a.type.value for a in artifacts])


# --- Module Notes -----------------------------------------------------------
# Used by `parallel_fetch_node` to compute missing artifacts accurately.
