from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uca_orchestrator.db.models import Artifact, ArtifactType


class ArtifactRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        *,
        use_case_id: uuid.UUID,
        type: ArtifactType,
        content: str,
        content_type: str = "text/markdown",
    ) -> Artifact:
        stmt = select(Artifact).where(Artifact.use_case_id == use_case_id, Artifact.type == type)
        existing = (await self._session.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            existing.content = content
            existing.content_type = content_type
            await self._session.flush()
            return existing

        art = Artifact(
            use_case_id=use_case_id, type=type, content=content, content_type=content_type
        )
        self._session.add(art)
        await self._session.flush()
        return art

    async def list_for_use_case(self, use_case_id: uuid.UUID) -> list[Artifact]:
        stmt = select(Artifact).where(Artifact.use_case_id == use_case_id)
        return list((await self._session.execute(stmt)).scalars().all())
