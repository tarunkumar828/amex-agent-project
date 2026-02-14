"""
uca_orchestrator.services.orchestration_service

Orchestration lifecycle service (transaction + persistence owner).

Responsibilities:
- Create runs and initialize orchestration state.
- Execute LangGraph with durable per-node checkpointing.
- Persist artifacts and audit events.
- Handle HITL interrupts and resume decisions.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from uca_orchestrator.db.models import ArtifactType, RunStatus, UseCaseStatus
from uca_orchestrator.db.repositories.artifacts import ArtifactRepo
from uca_orchestrator.db.repositories.audit import AuditRepo
from uca_orchestrator.db.repositories.runs import RunRepo
from uca_orchestrator.db.repositories.use_cases import UseCaseRepo
from uca_orchestrator.governance_clients.internal_http import InternalApiClient
from uca_orchestrator.orchestrator.graph import build_graph
from uca_orchestrator.orchestrator.interrupts import HumanInterrupt
from uca_orchestrator.orchestrator.state import UseCaseState
from uca_orchestrator.settings import Settings


class OrchestrationService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        http: httpx.AsyncClient,
    ) -> None:
        self._session = session
        self._settings = settings
        self._http = http

        self._use_cases = UseCaseRepo(session)
        self._runs = RunRepo(session)
        self._audit = AuditRepo(session)
        self._artifacts = ArtifactRepo(session)

    async def start(self, *, use_case_id: uuid.UUID, actor: str) -> uuid.UUID:
        uc = await self._use_cases.get(use_case_id)
        if uc is None:
            raise ValueError("use case not found")

        initial_state: UseCaseState = {
            "use_case_id": str(use_case_id),
            "submission_payload": uc.submission_payload,
            "classification": uc.classification or {},
            "missing_artifacts": uc.missing_artifacts or [],
            "approval_status": uc.approval_status or {},
            "eval_metrics": uc.eval_metrics or {},
            "risk_level": uc.risk_level or "UNKNOWN",
            "remediation_attempts": 0,
            "escalation_required": False,
            "audit_log": [],
        }

        run = await self._runs.create(use_case_id=use_case_id, initial_state=dict(initial_state))
        # Audit: run creation is attributed to the initiating actor.
        await self._audit.add(
            use_case_id=use_case_id,
            run_id=run.id,
            actor=actor,
            event_type="RUN_CREATED",
            details={},
        )
        await self._session.commit()
        return run.id

    async def execute(self, *, run_id: uuid.UUID, actor: str) -> dict[str, Any]:
        run = await self._runs.get(run_id)
        if run is None:
            raise ValueError("run not found")

        uc = await self._use_cases.get(run.use_case_id)
        if uc is None:
            raise ValueError("use case not found")

        # Tools client boundary: the graph calls governance systems via this interface.
        client = InternalApiClient(settings=self._settings, http=self._http)
        graph = build_graph(client=client, max_attempts=self._settings.max_remediation_attempts)

        state: UseCaseState = dict(run.state or {})
        state["use_case_id"] = str(uc.id)
        state["run_id"] = str(run.id)

        try:
            # Execute the graph using streaming updates so we can checkpoint after each node.
            final_state = await self._execute_with_checkpoints(
                graph=graph,
                use_case_id=uc.id,
                run_id=run.id,
                state=state,
            )
            await self._persist_state_success(
                use_case_id=uc.id,
                run_id=run.id,
                actor=actor,
                state=final_state,
            )
            await self._session.commit()
            return {"status": "APPROVAL_READY", "run_id": str(run.id), "use_case_id": str(uc.id)}
        except HumanInterrupt as hi:
            # Use the last persisted checkpoint as the interruption snapshot.
            refreshed = await self._runs.get(run_id)
            state_snapshot: UseCaseState = dict(
                refreshed.state if refreshed and refreshed.state else state
            )  # type: ignore[assignment]
            await self._persist_state_interrupt(
                use_case_id=uc.id,
                run_id=run.id,
                actor=actor,
                state=state_snapshot,
                interrupt=hi,
            )
            await self._session.commit()
            return {
                "status": "INTERRUPTED",
                "run_id": str(run.id),
                "use_case_id": str(uc.id),
                "reason": hi.reason,
            }
        except Exception as e:
            # Persist failure metadata for post-mortems / retries.
            await self._runs.set_state(
                run_id=run.id, status=RunStatus.failed, error=str(e), state=state
            )
            await self._use_cases.set_status(uc.id, UseCaseStatus.failed)
            await self._audit.add(
                use_case_id=uc.id,
                run_id=run.id,
                actor="agent",
                event_type="RUN_FAILED",
                details={"error": str(e)},
            )
            await self._session.commit()
            raise

    async def resume(
        self,
        *,
        run_id: uuid.UUID,
        actor: str,
        decision: dict[str, Any],
    ) -> dict[str, Any]:
        run = await self._runs.get(run_id)
        if run is None:
            raise ValueError("run not found")

        # Merge decision into state
        state: UseCaseState = dict(run.state or {})
        # HITL decisions are stored under `state["hitl"]["decision"]` so nodes can read them.
        hitl = dict(state.get("hitl", {}))
        hitl.update({"decision": decision})
        state["hitl"] = hitl

        await self._runs.set_state(
            run_id=run_id,
            status=RunStatus.running,
            interrupted_reason=None,
            interrupted_payload={},
            state=state,
        )
        await self._audit.add(
            use_case_id=run.use_case_id,
            run_id=run.id,
            actor=actor,
            event_type="RUN_RESUMED",
            details={"decision": decision},
        )
        await self._session.commit()
        return await self.execute(run_id=run_id, actor=actor)

    async def _persist_state_success(
        self,
        *,
        use_case_id: uuid.UUID,
        run_id: uuid.UUID,
        actor: str,
        state: UseCaseState,
    ) -> None:
        await self._runs.set_state(
            run_id=run_id,
            status=RunStatus.completed,
            state=dict(state),
            remediation_attempts=int(state.get("remediation_attempts", 0) or 0),
        )
        await self._use_cases.set_status(use_case_id, UseCaseStatus.approval_ready)
        await self._use_cases.patch_governance_snapshot(
            use_case_id=use_case_id,
            classification=state.get("classification", {}),
            approval_status=state.get("approval_status", {}),
            eval_metrics=state.get("eval_metrics", {}),
            missing_artifacts=state.get("missing_artifacts", []),
            risk_level=str(state.get("risk_level", "UNKNOWN")),
        )

        await self._persist_artifacts(use_case_id=use_case_id, state=state)
        await self._persist_audit(use_case_id=use_case_id, run_id=run_id, actor=actor, state=state)

    async def _persist_state_interrupt(
        self,
        *,
        use_case_id: uuid.UUID,
        run_id: uuid.UUID,
        actor: str,
        state: UseCaseState,
        interrupt: HumanInterrupt,
    ) -> None:
        await self._runs.set_state(
            run_id=run_id,
            status=RunStatus.interrupted,
            state=dict(state),
            remediation_attempts=int(state.get("remediation_attempts", 0) or 0),
            interrupted_reason=interrupt.reason,
            interrupted_payload=interrupt.payload,
        )
        await self._use_cases.set_status(use_case_id, UseCaseStatus.interrupted)
        await self._persist_audit(
            use_case_id=use_case_id,
            run_id=run_id,
            actor=actor,
            state=state,
        )
        await self._audit.add(
            use_case_id=use_case_id,
            run_id=run_id,
            actor="agent",
            event_type="HITL_INTERRUPT",
            details={"reason": interrupt.reason, "payload": interrupt.payload},
        )

    async def _persist_artifacts(self, *, use_case_id: uuid.UUID, state: UseCaseState) -> None:
        generated = state.get("_generated_artifacts")  # internal
        if not isinstance(generated, dict):
            return
        for k, v in generated.items():
            if not isinstance(v, str):
                continue
            art_type = _map_artifact_type(str(k))
            if art_type is None:
                continue
            await self._artifacts.upsert(use_case_id=use_case_id, type=art_type, content=v)

    async def _persist_audit(
        self,
        *,
        use_case_id: uuid.UUID,
        run_id: uuid.UUID,
        actor: str,
        state: UseCaseState,
    ) -> None:
        entries = state.get("audit_log", [])
        if not isinstance(entries, list):
            return
        start_idx = int(state.get("_audit_persisted_count", 0) or 0)
        for entry in entries[start_idx:]:
            if not isinstance(entry, dict):
                continue
            await self._audit.add(
                use_case_id=use_case_id,
                run_id=run_id,
                actor="agent",
                event_type=str(entry.get("event", "UNKNOWN")),
                details=dict(entry.get("details", {})),
            )

    async def _execute_with_checkpoints(
        self,
        *,
        graph: Any,
        use_case_id: uuid.UUID,
        run_id: uuid.UUID,
        state: UseCaseState,
    ) -> UseCaseState:
        """
        Doc alignment: persistence & checkpointing.
        We persist the run state after each node update (LangGraph stream_mode='updates').
        """

        last_state: UseCaseState = dict(state)
        persisted_audit_idx = 0

        # Some LangGraph versions support astream; keep a fallback to ainvoke.
        if not hasattr(graph, "astream"):
            return await graph.ainvoke(last_state)  # type: ignore[attr-defined]

        async for update in graph.astream(last_state, stream_mode="updates"):  # type: ignore[attr-defined]
            if not isinstance(update, dict) or not update:
                continue
            node_name, node_state = next(iter(update.items()))
            if isinstance(node_state, dict):
                last_state = node_state  # already a full state snapshot in this stream mode

            # Persist checkpoint (durable state snapshot).
            remediation_attempts = int(last_state.get("remediation_attempts", 0) or 0)
            last_state["_audit_persisted_count"] = persisted_audit_idx
            await self._runs.set_state(
                run_id=run_id,
                status=RunStatus.running,
                state=dict(last_state),
                remediation_attempts=remediation_attempts,
                error=None,
            )

            # Persist newly appended audit entries incrementally for crash recovery / replay.
            entries = last_state.get("audit_log", [])
            if isinstance(entries, list):
                for entry in entries[persisted_audit_idx:]:
                    if not isinstance(entry, dict):
                        continue
                    await self._audit.add(
                        use_case_id=use_case_id,
                        run_id=run_id,
                        actor="agent",
                        event_type=str(entry.get("event", "UNKNOWN")),
                        details={"node": node_name, **dict(entry.get("details", {}))},
                    )
                persisted_audit_idx = len(entries)
                last_state["_audit_persisted_count"] = persisted_audit_idx

            await self._session.commit()

        return last_state


def _map_artifact_type(raw: str) -> ArtifactType | None:
    mapping = {
        "REDACTION_PLAN": ArtifactType.redaction_plan,
        "MODEL_GOVERNANCE_ANSWERS": ArtifactType.model_governance_answers,
        "THREAT_MODEL": ArtifactType.threat_model,
        "AI_FIREWALL_RULES": ArtifactType.ai_firewall_rules,
        "APPROVAL_SUMMARY": ArtifactType.approval_summary,
    }
    return mapping.get(raw)


# --- Module Notes -----------------------------------------------------------
# This service is the transaction boundary: it decides when to commit checkpoints and how to
# map orchestrator state into durable DB entities (UseCase/Run/Artifact/AuditEvent).
