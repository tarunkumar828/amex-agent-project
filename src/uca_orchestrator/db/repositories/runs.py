"""
uca_orchestrator.db.repositories.runs

Repository for `Run` entities.

Responsibilities:
- Create and fetch orchestrator runs.
- Persist checkpoints (state snapshots) and interruption/error metadata.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from uca_orchestrator.db.models import Run, RunStatus


class RunRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, use_case_id: uuid.UUID, initial_state: dict[str, Any]) -> Run:
        # A new Run starts in RUNNING state with an initial state snapshot.
        run = Run(
            use_case_id=use_case_id,
            status=RunStatus.running,
            state=initial_state,
            remediation_attempts=0,
            interrupted_reason=None,
            interrupted_payload={},
            error=None,
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def get(self, run_id: uuid.UUID) -> Run | None:
        return await self._session.get(Run, run_id)

    async def latest_for_use_case(self, use_case_id: uuid.UUID) -> Run | None:
        stmt = (
            select(Run)
            .where(Run.use_case_id == use_case_id)
            .order_by(desc(Run.created_at))
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def set_state(
        self,
        *,
        run_id: uuid.UUID,
        status: RunStatus | None = None,
        state: dict[str, Any] | None = None,
        remediation_attempts: int | None = None,
        interrupted_reason: str | None = None,
        interrupted_payload: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        # Checkpoint/state updates are locked to avoid concurrent writers clobbering state.
        run = await self._session.get(Run, run_id, with_for_update=True)
        if run is None:
            return
        if status is not None:
            run.status = status
        if state is not None:
            run.state = state
        if remediation_attempts is not None:
            run.remediation_attempts = remediation_attempts
        if interrupted_reason is not None:
            run.interrupted_reason = interrupted_reason
        if interrupted_payload is not None:
            run.interrupted_payload = interrupted_payload
        if error is not None:
            run.error = error
        run.updated_at = datetime.utcnow()


# --- Module Notes -----------------------------------------------------------
# In this repo, checkpoints are written after each LangGraph node execution.
