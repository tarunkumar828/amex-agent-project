from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt import InvalidTokenError


@dataclass(frozen=True, slots=True)
class JwtConfig:
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
