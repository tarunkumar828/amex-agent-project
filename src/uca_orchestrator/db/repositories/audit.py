from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from uca_orchestrator.db.models import AuditEvent


class AuditRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        use_case_id: uuid.UUID,
        run_id: uuid.UUID | None,
        actor: str,
        event_type: str,
        details: dict[str, Any],
    ) -> AuditEvent:
        ev = AuditEvent(
            use_case_id=use_case_id,
            run_id=run_id,
            actor=actor,
            event_type=event_type,
            details=details,
        )
        self._session.add(ev)
        await self._session.flush()
        return ev

    async def list_for_use_case(
        self, use_case_id: uuid.UUID, *, limit: int = 200
    ) -> list[AuditEvent]:
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.use_case_id == use_case_id)
            .order_by(desc(AuditEvent.created_at))
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars().all())
