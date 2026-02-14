from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uca_orchestrator.db.models import UseCase, UseCaseStatus


class UseCaseRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        owner: str,
        submission_payload: dict[str, Any],
        external_use_case_id: str | None = None,
    ) -> UseCase:
        uc = UseCase(
            owner=owner,
            submission_payload=submission_payload,
            external_use_case_id=external_use_case_id,
            classification={},
            approval_status={},
            eval_metrics={},
            missing_artifacts=[],
            risk_level="UNKNOWN",
            status=UseCaseStatus.registered,
        )
        self._session.add(uc)
        await self._session.flush()
        return uc

    async def get(self, use_case_id: uuid.UUID) -> UseCase | None:
        return await self._session.get(UseCase, use_case_id)

    async def get_by_external_id(self, external_use_case_id: str) -> UseCase | None:
        stmt = select(UseCase).where(UseCase.external_use_case_id == external_use_case_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def set_status(self, use_case_id: uuid.UUID, status: UseCaseStatus) -> None:
        uc = await self._session.get(UseCase, use_case_id, with_for_update=True)
        if uc is None:
            return
        uc.status = status
        uc.updated_at = datetime.utcnow()

    async def patch_governance_snapshot(
        self,
        *,
        use_case_id: uuid.UUID,
        classification: dict[str, Any] | None = None,
        approval_status: dict[str, Any] | None = None,
        eval_metrics: dict[str, Any] | None = None,
        missing_artifacts: list[str] | None = None,
        risk_level: str | None = None,
    ) -> None:
        uc = await self._session.get(UseCase, use_case_id, with_for_update=True)
        if uc is None:
            return
        if classification is not None:
            uc.classification = classification
        if approval_status is not None:
            uc.approval_status = approval_status
        if eval_metrics is not None:
            uc.eval_metrics = eval_metrics
        if missing_artifacts is not None:
            uc.missing_artifacts = missing_artifacts
        if risk_level is not None:
            uc.risk_level = risk_level
        uc.updated_at = datetime.utcnow()
