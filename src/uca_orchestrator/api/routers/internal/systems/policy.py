from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from uca_orchestrator.auth.deps import require_roles

router = APIRouter(dependencies=[Depends(require_roles("internal_system"))])


class PolicyRequest(BaseModel):
    data_classification: Literal["PCI", "NON_PCI", "UNKNOWN"] = "UNKNOWN"
    deployment_target: Literal["CLOUD", "ON_PREM", "UNKNOWN"] = "UNKNOWN"
    model_provider: Literal["INTERNAL", "EXTERNAL", "UNKNOWN"] = "UNKNOWN"


class PolicyResponse(BaseModel):
    required_artifacts: list[str] = Field(default_factory=list)
    required_evaluations: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


@router.post("/requirements", response_model=PolicyResponse)
async def get_policy_requirements(body: PolicyRequest) -> PolicyResponse:
    required_artifacts: list[str] = []
    required_evaluations: list[str] = []

    if body.data_classification == "PCI":
        required_artifacts += ["REDACTION_PLAN", "THREAT_MODEL"]
        required_evaluations += ["REDACTABILITY", "TOXICITY", "PROMPT_INJECTION"]
    else:
        required_artifacts += ["MODEL_GOVERNANCE_ANSWERS"]
        required_evaluations += ["TOXICITY"]

    if body.deployment_target == "CLOUD":
        required_artifacts += ["AI_FIREWALL_RULES"]
        required_evaluations += ["NETSEC_BASELINE"]

    if body.model_provider == "EXTERNAL":
        required_artifacts += ["AI_FIREWALL_RULES"]

    # de-dupe while keeping order
    required_artifacts = list(dict.fromkeys(required_artifacts))
    required_evaluations = list(dict.fromkeys(required_evaluations))

    return PolicyResponse(
        required_artifacts=required_artifacts,
        required_evaluations=required_evaluations,
        meta={"policy_version": "dummy-2026-02-12"},
    )
