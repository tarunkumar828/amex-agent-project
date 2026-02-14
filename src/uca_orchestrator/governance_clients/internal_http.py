"""
uca_orchestrator.governance_clients.internal_http

HTTP client boundary used by the orchestrator to call governance systems.

Responsibilities:
- Attach short-lived JWT credentials (role=internal_system).
- Call internal dummy governance endpoints under `/internal/v1/*`.
- Provide a stable interface that can later be swapped to real services.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal

import httpx

from uca_orchestrator.auth.jwt import JwtConfig, issue_token
from uca_orchestrator.settings import Settings


@dataclass(frozen=True, slots=True)
class InternalApiAuth:
    # Identity used for tool calls; subject is an internal service identity.
    subject: str = "uca-service"
    roles: tuple[str, ...] = ("internal_system",)


class InternalApiClient:
    """
    Enterprise boundary:
    - The orchestrator talks to governance systems via a client interface.
    - In this repo, those systems are implemented as JWT-protected internal routes.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        http: httpx.AsyncClient,
        auth: InternalApiAuth | None = None,
    ) -> None:
        self._settings = settings
        self._http = http
        self._auth = auth or InternalApiAuth()

    def _authz(self) -> dict[str, str]:
        # Tool auth: mint a short-lived token so internal endpoints can enforce RBAC.
        cfg = JwtConfig(
            alg=self._settings.jwt_alg,
            issuer=self._settings.jwt_issuer,
            audience=self._settings.jwt_audience,
            secret=self._settings.jwt_secret,
        )
        token = issue_token(
            cfg=cfg,
            subject=self._auth.subject,
            roles=list(self._auth.roles),
            ttl=timedelta(minutes=5),
        )
        return {"Authorization": f"Bearer {token}"}

    async def registration_status(self, *, use_case_id: uuid.UUID) -> dict[str, Any]:
        # Registration: authoritative submission payload snapshot.
        r = await self._http.get(
            f"/internal/v1/registration/{use_case_id}/status",
            headers=self._authz(),
        )
        r.raise_for_status()
        return r.json()

    async def policy_requirements(
        self,
        *,
        data_classification: Literal["PCI", "NON_PCI", "UNKNOWN"],
        deployment_target: Literal["CLOUD", "ON_PREM", "UNKNOWN"],
        model_provider: Literal["INTERNAL", "EXTERNAL", "UNKNOWN"],
    ) -> dict[str, Any]:
        # Policy: dynamic requirements based on classification.
        r = await self._http.post(
            "/internal/v1/policy/requirements",
            headers=self._authz(),
            json={
                "data_classification": data_classification,
                "deployment_target": deployment_target,
                "model_provider": model_provider,
            },
        )
        r.raise_for_status()
        return r.json()

    async def approval_status(self, *, use_case_id: uuid.UUID) -> dict[str, Any]:
        # Approvals: returns system-by-system approval decisions.
        r = await self._http.get(
            f"/internal/v1/approvals/{use_case_id}/status",
            headers=self._authz(),
        )
        r.raise_for_status()
        return r.json()

    async def artifact_status(self, *, use_case_id: uuid.UUID) -> dict[str, Any]:
        # Artifact status is used by gap analysis (required vs present).
        r = await self._http.get(
            f"/internal/v1/artifacts/{use_case_id}/status",
            headers=self._authz(),
        )
        r.raise_for_status()
        return r.json()

    async def trigger_evaluations(
        self, *, use_case_id: uuid.UUID, evaluations: list[str]
    ) -> dict[str, Any]:
        # Evaluations: trigger required checks; dummy impl writes metrics snapshots.
        r = await self._http.post(
            f"/internal/v1/evaluations/{use_case_id}/trigger",
            headers=self._authz(),
            json={"evaluations": evaluations},
        )
        r.raise_for_status()
        return r.json()

    async def eval_status(self, *, use_case_id: uuid.UUID) -> dict[str, Any]:
        r = await self._http.get(
            f"/internal/v1/evaluations/{use_case_id}/status",
            headers=self._authz(),
        )
        r.raise_for_status()
        return r.json()

    async def netsec_baseline(self, *, use_case_id: uuid.UUID) -> dict[str, Any]:
        r = await self._http.get(
            f"/internal/v1/netsec/{use_case_id}/baseline",
            headers=self._authz(),
        )
        r.raise_for_status()
        return r.json()

    async def firewall_check(self, *, use_case_id: uuid.UUID) -> dict[str, Any]:
        r = await self._http.get(
            f"/internal/v1/firewall/{use_case_id}/check",
            headers=self._authz(),
        )
        r.raise_for_status()
        return r.json()

    async def hydra_readiness(self, *, use_case_id: uuid.UUID) -> dict[str, Any]:
        r = await self._http.get(
            f"/internal/v1/hydra/{use_case_id}/readiness",
            headers=self._authz(),
        )
        r.raise_for_status()
        return r.json()


# --- Module Notes -----------------------------------------------------------
# This client intentionally mimics a real org pattern:
# - mTLS / service-to-service auth would replace HS256 in production
# - base_url and timeouts/retries would be configured per environment
