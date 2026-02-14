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

router.include_router(registration.router, prefix="/registration")
router.include_router(policy.router, prefix="/policy")
router.include_router(approvals.router, prefix="/approvals")
router.include_router(artifacts.router, prefix="/artifacts")
router.include_router(evaluations.router, prefix="/evaluations")
router.include_router(netsec.router, prefix="/netsec")
router.include_router(firewall.router, prefix="/firewall")
router.include_router(hydra.router, prefix="/hydra")
