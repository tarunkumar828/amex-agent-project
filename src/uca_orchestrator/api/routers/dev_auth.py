from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette.status import HTTP_404_NOT_FOUND

from uca_orchestrator.auth.jwt import JwtConfig, issue_token
from uca_orchestrator.settings import Settings, get_settings

router = APIRouter(prefix="/v1/dev", tags=["dev"])


class DevTokenRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=256)
    roles: list[str] = Field(default_factory=list)
    ttl_minutes: int = Field(default=60, ge=1, le=24 * 60)


class DevTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/token", response_model=DevTokenResponse)
async def mint_dev_token(
    body: DevTokenRequest,
    settings: Settings = Depends(get_settings),
) -> DevTokenResponse:
    if settings.env == "prod":
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Not found")

    cfg = JwtConfig(
        alg=settings.jwt_alg,
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        secret=settings.jwt_secret,
    )
    token = issue_token(
        cfg=cfg,
        subject=body.subject,
        roles=body.roles,
        ttl=timedelta(minutes=body.ttl_minutes),
    )
    return DevTokenResponse(access_token=token)
