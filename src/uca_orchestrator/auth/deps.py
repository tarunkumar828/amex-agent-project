"""
uca_orchestrator.auth.deps

FastAPI dependency functions for authentication and authorization.

Responsibilities:
- Convert a bearer token into a typed `Principal`.
- Enforce RBAC via reusable dependency factories.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

from uca_orchestrator.auth.jwt import JwtConfig, JwtValidationError, decode_and_validate
from uca_orchestrator.auth.models import Principal
from uca_orchestrator.settings import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)


def _jwt_cfg(settings: Settings) -> JwtConfig:
    return JwtConfig(
        alg=settings.jwt_alg,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        secret=settings.jwt_secret,
    )


def get_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> Principal:
    # Authn: require a bearer token.
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    try:
        # Authn: validate signature and registered claims (iss/aud/exp/sub...).
        payload = decode_and_validate(cfg=_jwt_cfg(settings), token=creds.credentials)
    except JwtValidationError as e:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}") from e

    # Normalize identity into our internal type.
    subject = str(payload.get("sub", ""))
    roles_raw = payload.get("roles", [])
    if not subject:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Invalid token subject")
    if not isinstance(roles_raw, list):
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Invalid token roles")

    roles: frozenset[str] = frozenset(str(r) for r in roles_raw)
    return Principal(subject=subject, roles=roles)


def require_roles(*required: str):
    required_set = frozenset(required)

    def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        # Authz: admin is allowed to bypass role checks (ops/debug).
        if principal.is_admin:
            return principal
        if not required_set.issubset(principal.roles):
            raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Insufficient role")
        return principal

    return _dep


# --- Module Notes -----------------------------------------------------------
# These dependencies are used for both:
# - External/public endpoints (use case owner, governance reviewer)
# - Internal tool endpoints (role=internal_system)
