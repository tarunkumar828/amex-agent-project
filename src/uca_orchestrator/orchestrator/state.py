"""
uca_orchestrator.orchestrator.state

Typed state schema used by the LangGraph orchestration engine.

Responsibilities:
- Define the contract between nodes (inputs/outputs).
- Provide a stable shape for persistence (stored in runs.state).
"""

from __future__ import annotations

from typing import Any, TypedDict


class UseCaseState(TypedDict, total=False):
    # Identifiers
    use_case_id: str
    run_id: str

    # Inputs/snapshots
    submission_payload: dict[str, Any]
    classification: dict[str, Any]

    # Governance view
    missing_artifacts: list[str]
    approval_status: dict[str, Any]
    eval_metrics: dict[str, Any]

    # Orchestration controls
    risk_level: str
    remediation_attempts: int
    escalation_required: bool

    # Audit
    audit_log: list[dict[str, Any]]

    # HITL
    hitl: dict[str, Any]


# --- Module Notes -----------------------------------------------------------
# This TypedDict is intentionally permissive (total=False) because LangGraph nodes may
# stage internal/transient keys while still producing a valid persisted snapshot.
