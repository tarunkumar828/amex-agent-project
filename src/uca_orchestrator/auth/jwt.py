"""
uca_orchestrator.auth.jwt

JWT issuing and validation helpers.

Responsibilities:
- Issue short-lived JWTs for local/dev scenarios and internal tool calls.
- Decode and validate JWTs with strict claim requirements (iss/aud/exp/iat/sub).

Note:
- Production systems often prefer RS256 + JWKS; this repo uses HS256 for simplicity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt import InvalidTokenError


@dataclass(frozen=True, slots=True)
class JwtConfig:
    # Algorithm/issuer/audience are enforced during decoding.
    alg: str
    issuer: str
    audience: str
    secret: str


class JwtValidationError(Exception):
    pass


def issue_token(
    *,
    cfg: JwtConfig,
    subject: str,
    roles: list[str],
    ttl: timedelta = timedelta(hours=1),
) -> str:
    now = datetime.now(tz=UTC)
    # Keep payload minimal and stable; downstream services should avoid parsing arbitrary fields.
    payload: dict[str, Any] = {
        "iss": cfg.issuer,
        "aud": cfg.audience,
        "sub": subject,
        "roles": roles,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(payload, cfg.secret, algorithm=cfg.alg)


def decode_and_validate(*, cfg: JwtConfig, token: str) -> dict[str, Any]:
    try:
        # jwt.decode enforces signature + registered claims (issuer/audience/exp, etc.).
        return jwt.decode(
            token,
            cfg.secret,
            algorithms=[cfg.alg],
            issuer=cfg.issuer,
            audience=cfg.audience,
            options={
                "require": ["exp", "iat", "iss", "aud", "sub"],
            },
        )
    except InvalidTokenError as e:
        raise JwtValidationError(str(e)) from e


# --- Module Notes -----------------------------------------------------------
# Token issuing is used by:
# - `api/routers/dev_auth.py` (dev convenience)
# - `governance_clients/internal_http.py` (tool auth for internal endpoints)
