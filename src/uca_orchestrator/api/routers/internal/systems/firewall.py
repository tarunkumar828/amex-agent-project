from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from uca_orchestrator.api.deps import db_session
from uca_orchestrator.auth.deps import require_roles
from uca_orchestrator.db.models import ArtifactType
from uca_orchestrator.db.repositories.artifacts import ArtifactRepo

router = APIRouter(dependencies=[Depends(require_roles("internal_system"))])


class FirewallResponse(BaseModel):
    status: Literal["PASS", "FAIL", "PENDING"]
    notes: str | None = None


@router.get("/{use_case_id}/check", response_model=FirewallResponse)
async def firewall_check(
    use_case_id: uuid.UUID,
    session: AsyncSession = Depends(db_session),
) -> FirewallResponse:
    artifacts = await ArtifactRepo(session).list_for_use_case(use_case_id)
    has_rules = any(a.type == ArtifactType.ai_firewall_rules for a in artifacts)
    if has_rules:
        return FirewallResponse(status="PASS", notes="Dummy firewall rules present")
    return FirewallResponse(status="PENDING", notes="Firewall rules missing")
