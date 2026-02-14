"""
uca_orchestrator.db.models

Core persistence schema for the orchestrator.

Responsibilities:
- Define ORM models representing long-running approvals:
  - UseCase: business entity and governance snapshots
  - Run: durable orchestration run state + interrupt context
  - Artifact: generated documents/rulesets
  - AuditEvent: append-only audit trail
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Enum, ForeignKey, Index, String, Text, Uuid as SAUuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from uca_orchestrator.db.base import Base


def _utcnow() -> datetime:
    # Persist naive UTC timestamps for simplicity; production systems may use tz-aware types.
    return datetime.utcnow()


class UseCaseStatus(enum.StrEnum):
    # High-level business status of a use case as observed by the orchestration service.
    registered = "REGISTERED"
    in_progress = "IN_PROGRESS"
    interrupted = "INTERRUPTED"
    escalated = "ESCALATED"
    approval_ready = "APPROVAL_READY"
    failed = "FAILED"


class RunStatus(enum.StrEnum):
    # Execution status of a particular orchestrator run.
    running = "RUNNING"
    interrupted = "INTERRUPTED"
    completed = "COMPLETED"
    failed = "FAILED"


class ArtifactType(enum.StrEnum):
    # Enum values are stored in DB; treat as stable API contract.
    redaction_plan = "REDACTION_PLAN"
    model_governance_answers = "MODEL_GOVERNANCE_ANSWERS"
    threat_model = "THREAT_MODEL"
    ai_firewall_rules = "AI_FIREWALL_RULES"
    approval_summary = "APPROVAL_SUMMARY"


class UseCase(Base):
    __tablename__ = "use_cases"

    id: Mapped[uuid.UUID] = mapped_column(
        SAUuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    external_use_case_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    owner: Mapped[str] = mapped_column(String(256), nullable=False)

    submission_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    classification: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    approval_status: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    eval_metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    risk_level: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN")
    missing_artifacts: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    status: Mapped[UseCaseStatus] = mapped_column(Enum(UseCaseStatus), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow, onupdate=_utcnow)

    runs: Mapped[list[Run]] = relationship(back_populates="use_case", cascade="all, delete-orphan")
    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="use_case", cascade="all, delete-orphan"
    )


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(
        SAUuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    use_case_id: Mapped[uuid.UUID] = mapped_column(
        SAUuid(as_uuid=True), ForeignKey("use_cases.id"), nullable=False, index=True
    )

    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), nullable=False, index=True)
    # `state` stores the LangGraph state snapshot (checkpointed per node execution).
    state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    remediation_attempts: Mapped[int] = mapped_column(nullable=False, default=0)

    interrupted_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    interrupted_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow, onupdate=_utcnow)

    use_case: Mapped[UseCase] = relationship(back_populates="runs")

    __table_args__ = (Index("ix_runs_use_case_created", "use_case_id", "created_at"),)


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(
        SAUuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    use_case_id: Mapped[uuid.UUID] = mapped_column(
        SAUuid(as_uuid=True), ForeignKey("use_cases.id"), nullable=False, index=True
    )

    type: Mapped[ArtifactType] = mapped_column(Enum(ArtifactType), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False, default="text/markdown")

    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)

    use_case: Mapped[UseCase] = relationship(back_populates="artifacts")

    __table_args__ = (Index("ix_artifacts_use_case_type", "use_case_id", "type"),)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        SAUuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    use_case_id: Mapped[uuid.UUID] = mapped_column(SAUuid(as_uuid=True), nullable=False, index=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        SAUuid(as_uuid=True), nullable=True, index=True
    )

    actor: Mapped[str] = mapped_column(String(256), nullable=False)  # user id / agent / system
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow, index=True)

    __table_args__ = (Index("ix_audit_use_case_created", "use_case_id", "created_at"),)


# --- Module Notes -----------------------------------------------------------
# JSON columns keep this example flexible across governance payload variations.
# In stricter environments, consider schema-versioned JSON and validation at write time.
