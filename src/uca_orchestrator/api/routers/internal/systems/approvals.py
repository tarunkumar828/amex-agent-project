"""
uca_orchestrator.api.routers.internal.systems.approvals

Dummy approvals system.

Responsibilities:
- Compute system-by-system approval decisions from persisted snapshots.
- Write the current approval snapshot back into the UseCase record.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_404_NOT_FOUND

from uca_orchestrator.api.deps import db_session
from uca_orchestrator.auth.deps import require_roles
from uca_orchestrator.db.repositories.use_cases import UseCaseRepo

router = APIRouter(dependencies=[Depends(require_roles("internal_system"))])


ApprovalState = Literal["PENDING", "APPROVED", "REJECTED"]


class ApprovalItem(BaseModel):
    system: str
    state: ApprovalState
    comment: str | None = None


class ApprovalStatusResponse(BaseModel):
    approvals: list[ApprovalItem] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


@router.get("/{use_case_id}/status", response_model=ApprovalStatusResponse)
async def get_approval_status(
    use_case_id: uuid.UUID,
    session: AsyncSession = Depends(db_session),
) -> ApprovalStatusResponse:
    # Internal auth is enforced at router creation: role=internal_system.
    repo = UseCaseRepo(session)
    uc = await repo.get(use_case_id)
    if uc is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Use case not found")

    missing = set(uc.missing_artifacts or [])
    metrics = uc.eval_metrics or {}

    toxicity = float(metrics.get("toxicity", 0.0) or 0.0)
    prompt_inj = float(metrics.get("prompt_injection", 0.0) or 0.0)

    approvals: list[ApprovalItem] = []

    # Model governance (example rule: reject if governance Q&A is missing).
    if "MODEL_GOVERNANCE_ANSWERS" in missing:
        approvals.append(
            ApprovalItem(
                system="MODEL_GOVERNANCE", state="REJECTED", comment="Missing governance Q&A"
            )
        )
    else:
        approvals.append(ApprovalItem(system="MODEL_GOVERNANCE", state="APPROVED"))

    # NetSec (example rule: reject if threat model is missing).
    if "THREAT_MODEL" in missing:
        approvals.append(
            ApprovalItem(system="NETSECOPS", state="REJECTED", comment="Threat model missing")
        )
    else:
        approvals.append(ApprovalItem(system="NETSECOPS", state="APPROVED"))

    # Risk/compliance: reject if toxicity too high.
    if toxicity > 0.07:
        approvals.append(
            ApprovalItem(
                system="RISK", state="REJECTED", comment=f"Toxicity too high: {toxicity:.2f}"
            )
        )
    else:
        approvals.append(ApprovalItem(system="RISK", state="APPROVED"))

    # AI firewall: require rules if prompt injection too high and rules are missing.
    if prompt_inj > 0.07 and "AI_FIREWALL_RULES" in missing:
        approvals.append(
            ApprovalItem(system="AI_FIREWALL", state="REJECTED", comment="Firewall rules required")
        )
    else:
        approvals.append(ApprovalItem(system="AI_FIREWALL", state="APPROVED"))

    snapshot = {a.system: {"state": a.state, "comment": a.comment} for a in approvals}
    await repo.patch_governance_snapshot(use_case_id=use_case_id, approval_status=snapshot)
    await session.commit()

    return ApprovalStatusResponse(approvals=approvals, meta={"source": "dummy"})


# --- Module Notes -----------------------------------------------------------
# Approvals are read by the orchestrator during parallel fetch and approval_check.
