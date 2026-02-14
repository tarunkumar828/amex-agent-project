"""
uca_orchestrator.api.routers.internal.systems.evaluations

Dummy evaluation system.

Responsibilities:
- Trigger evaluation runs and persist derived metrics.
- Provide the current eval metrics snapshot for a use case.
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

router = APIRouter(dependencies=[Depends(require_roles("internal_system"))])


class TriggerEvalRequest(BaseModel):
    evaluations: list[str] = Field(default_factory=list)


class EvalStatusResponse(BaseModel):
    eval_metrics: dict[str, Any]


@router.post("/{use_case_id}/trigger", response_model=EvalStatusResponse)
async def trigger_evaluations(
    use_case_id: uuid.UUID,
    body: TriggerEvalRequest,
    session: AsyncSession = Depends(db_session),
) -> EvalStatusResponse:
    repo = UseCaseRepo(session)
    uc = await repo.get(use_case_id)
    if uc is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Use case not found")

    # Dummy metrics: predictable and slightly strict for PCI to force remediation/escalation paths.
    cls = (uc.classification or {}).get("data_classification", "UNKNOWN")
    base_toxicity = 0.03 if cls == "NON_PCI" else 0.08 if cls == "PCI" else 0.05
    metrics = dict(uc.eval_metrics or {})
    for ev in body.evaluations:
        if ev == "TOXICITY":
            metrics["toxicity"] = base_toxicity
        elif ev == "PROMPT_INJECTION":
            metrics["prompt_injection"] = 0.04 if cls != "PCI" else 0.09
        elif ev == "REDACTABILITY":
            metrics["redactability"] = 0.98 if cls == "PCI" else 0.9
        elif ev == "NETSEC_BASELINE":
            metrics["netsec_baseline"] = "PASS"
        else:
            metrics[ev.lower()] = "PASS"

    await repo.patch_governance_snapshot(use_case_id=use_case_id, eval_metrics=metrics)
    await session.commit()
    return EvalStatusResponse(eval_metrics=metrics)


@router.get("/{use_case_id}/status", response_model=EvalStatusResponse)
async def get_eval_status(
    use_case_id: uuid.UUID,
    session: AsyncSession = Depends(db_session),
) -> EvalStatusResponse:
    uc = await UseCaseRepo(session).get(use_case_id)
    if uc is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Use case not found")
    return EvalStatusResponse(eval_metrics=uc.eval_metrics or {})


# --- Module Notes -----------------------------------------------------------
# The orchestrator triggers evals via InternalApiClient in `eval_check_node`.
