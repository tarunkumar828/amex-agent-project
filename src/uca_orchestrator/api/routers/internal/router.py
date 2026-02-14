"""
uca_orchestrator.api.routers.internal.router

Internal tool router aggregator.

Responsibilities:
- Mount per-system internal routers under `/internal/v1`.
- Present a stable internal tool API surface for the orchestrator.
"""

from __future__ import annotations

from fastapi import APIRouter

from uca_orchestrator.api.routers.internal.systems import (
    approvals,
    artifacts,
    evaluations,
    firewall,
    hydra,
    netsec,
    policy,
    registration,
)

router = APIRouter(prefix="/internal/v1", tags=["internal"])

## Each included router is protected by RBAC role `internal_system`.
router.include_router(registration.router, prefix="/registration")
router.include_router(policy.router, prefix="/policy")
router.include_router(approvals.router, prefix="/approvals")
router.include_router(artifacts.router, prefix="/artifacts")
router.include_router(evaluations.router, prefix="/evaluations")
router.include_router(netsec.router, prefix="/netsec")
router.include_router(firewall.router, prefix="/firewall")
router.include_router(hydra.router, prefix="/hydra")


# --- Module Notes -----------------------------------------------------------
# These endpoints simulate external/internal governance systems while keeping the repo self-contained.
