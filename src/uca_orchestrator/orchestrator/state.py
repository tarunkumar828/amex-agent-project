"""
uca_orchestrator.orchestrator.state

Typed state schema used by the LangGraph orchestration engine.

Responsibilities:
- Define the contract between nodes (inputs/outputs).
- Provide a stable shape for persistence (stored in runs.state).
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from uca_orchestrator.orchestrator.reducers import append_audit, merge_dicts


class UseCaseState(TypedDict, total=False):
    # Identifiers
    use_case_id: str
    run_id: str

    # Inputs/snapshots
    submission_payload: dict[str, Any]
    classification: Annotated[dict[str, Any], merge_dicts]

    # Governance view
    missing_artifacts: list[str]
    approval_status: Annotated[dict[str, Any], merge_dicts]
    eval_metrics: Annotated[dict[str, Any], merge_dicts]

    # Policy + artifact presence (used for gap analysis)
    policy: dict[str, Any]
    artifact_types_present: list[str]

    # Generated artifacts (persisted by service layer)
    generated_artifacts: dict[str, str]

    # Orchestration controls
    risk_level: str
    remediation_attempts: int
    escalation_required: bool

    # Derived control flags (kept explicit for routing)
    eval_failed: dict[str, Any] | None
    approval_rejected: dict[str, Any] | None

    # Audit
    audit_log: Annotated[list[dict[str, Any]], append_audit]

    # HITL
    hitl: dict[str, Any]

    # Internal bookkeeping for incremental persistence (service layer).
    _audit_persisted_count: int


# --- Module Notes -----------------------------------------------------------
# This TypedDict is intentionally permissive (total=False) because LangGraph nodes may
# stage internal/transient keys while still producing a valid persisted snapshot.
