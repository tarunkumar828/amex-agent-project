"""
uca_orchestrator.orchestrator.nodes

LangGraph node implementations + routing functions.

Responsibilities:
- Implement each step in the approval-orchestration lifecycle:
  ENTRY, CLASSIFY, PARALLEL_FETCH, GAP_ANALYSIS, ARTIFACT_GENERATION,
  EVAL_CHECK, APPROVAL_CHECK, REMEDIATION, ESCALATION, FINISH.
- Append structured audit events into state (later persisted to DB).
- Keep node logic deterministic and testable (no direct DB writes).
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from uca_orchestrator.governance_clients.internal_http import InternalApiClient
from uca_orchestrator.orchestrator.interrupts import HumanInterrupt
from uca_orchestrator.orchestrator.state import UseCaseState


def _audit(event: str, details: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Produce a single audit entry. Reducer `append_audit` concatenates these across nodes.
    """

    return [{"event": event, "details": details}]


async def entry_node(state: UseCaseState) -> UseCaseState:
    """
    Spec alignment:
    - Validate input
    - Initialize state defaults
    """

    if "use_case_id" not in state or not str(state.get("use_case_id", "")).strip():
        raise ValueError("Missing use_case_id")
    if "submission_payload" in state and not isinstance(state["submission_payload"], dict):
        raise ValueError("submission_payload must be a dict")

    # Entry initializes stable defaults. This node runs first, so overwrites are safe.
    return {
        "use_case_id": state["use_case_id"],
        "submission_payload": state.get("submission_payload", {}),
        "classification": state.get("classification", {}),
        "missing_artifacts": state.get("missing_artifacts", []),
        "approval_status": state.get("approval_status", {}),
        "eval_metrics": state.get("eval_metrics", {}),
        "policy": state.get("policy", {}),
        "artifact_types_present": state.get("artifact_types_present", []),
        "risk_level": state.get("risk_level", "UNKNOWN"),
        "remediation_attempts": int(state.get("remediation_attempts", 0) or 0),
        "escalation_required": bool(state.get("escalation_required", False)),
        "eval_failed": state.get("eval_failed"),
        "approval_rejected": state.get("approval_rejected"),
        "audit_log": _audit("ENTRY", {}),
    }


async def classify_node(state: UseCaseState) -> UseCaseState:
    # Minimal deterministic classification from the submission payload.
    payload = state.get("submission_payload", {})

    data_classification = (payload.get("data_classification") or "UNKNOWN").upper()
    deployment_target = (payload.get("deployment_target") or "UNKNOWN").upper()
    model_provider = (payload.get("model_provider") or "UNKNOWN").upper()

    risk = "LOW"
    if data_classification == "PCI" or model_provider == "EXTERNAL":
        risk = "HIGH"
    elif deployment_target == "CLOUD":
        risk = "MEDIUM"

    classification = {
        "data_classification": data_classification,
        "deployment_target": deployment_target,
        "model_provider": model_provider,
    }
    return {
        "classification": classification,
        "risk_level": risk,
        "audit_log": _audit("CLASSIFY", {"risk_level": risk, **classification}),
    }

async def fetch_registration_node(state: UseCaseState, *, client: InternalApiClient) -> UseCaseState:
    use_case_id = state["use_case_id"]
    reg = await client.registration_status(use_case_id=_uuid(use_case_id))
    payload = reg.get("submission_payload", {})
    return {"submission_payload": payload, "audit_log": _audit("FETCH_REGISTRATION", {})}


async def fetch_policy_node(state: UseCaseState, *, client: InternalApiClient) -> UseCaseState:
    cls = state.get("classification", {})
    policy = await client.policy_requirements(
        data_classification=_lit(str(cls.get("data_classification", "UNKNOWN"))),
        deployment_target=_lit(str(cls.get("deployment_target", "UNKNOWN"))),
        model_provider=_lit(str(cls.get("model_provider", "UNKNOWN"))),
    )
    return {"policy": policy, "audit_log": _audit("FETCH_POLICY", {"meta": policy.get("meta", {})})}


async def fetch_approvals_node(state: UseCaseState, *, client: InternalApiClient) -> UseCaseState:
    use_case_id = state["use_case_id"]
    approvals = await client.approval_status(use_case_id=_uuid(use_case_id))
    snapshot = _normalize_approval_snapshot(approvals)
    return {"approval_status": snapshot, "audit_log": _audit("FETCH_APPROVALS", {})}


async def fetch_eval_status_node(state: UseCaseState, *, client: InternalApiClient) -> UseCaseState:
    use_case_id = state["use_case_id"]
    evals = await client.eval_status(use_case_id=_uuid(use_case_id))
    metrics = evals.get("eval_metrics", {})
    return {"eval_metrics": metrics, "audit_log": _audit("FETCH_EVAL_STATUS", {})}


async def fetch_artifacts_status_node(state: UseCaseState, *, client: InternalApiClient) -> UseCaseState:
    use_case_id = state["use_case_id"]
    artifacts = await client.artifact_status(use_case_id=_uuid(use_case_id))
    present = list(artifacts.get("artifact_types", []))
    return {"artifact_types_present": present, "audit_log": _audit("FETCH_ARTIFACT_STATUS", {})}


def _normalize_approval_snapshot(approvals_resp: dict[str, Any]) -> dict[str, Any]:
    # Internal dummy returns {"approvals": [{"system":..., "state":...}, ...]}
    items = approvals_resp.get("approvals", [])
    out: dict[str, Any] = {}
    if isinstance(items, list):
        for it in items:
            system = str(it.get("system", "UNKNOWN"))
            out[system] = {"state": it.get("state"), "comment": it.get("comment")}
    return out


async def gap_analysis_node(state: UseCaseState) -> UseCaseState:
    # Compare policy requirements to the artifact types present in persistence.
    policy = state.get("policy", {})
    required = list(policy.get("required_artifacts", []))
    missing: list[str] = []

    present = set(state.get("artifact_types_present", []))
    for a in required:
        if str(a) in present:
            continue
        missing.append(str(a))

    return {"missing_artifacts": missing, "audit_log": _audit("GAP_ANALYSIS", {"required": required, "missing": missing})}


async def artifact_generation_node(state: UseCaseState) -> UseCaseState:
    # Dummy artifact generation. In production, this would call an LLM or template engine.
    missing = list(state.get("missing_artifacts", []))
    generated = {}
    for art in missing:
        generated[art] = _generate_artifact(artifact_type=art, state=state)

    # Note: missing_artifacts is cleared after generation in this dummy system.
    return {
        "generated_artifacts": generated,
        "missing_artifacts": [],
        "audit_log": _audit("ARTIFACT_GENERATION", {"generated": list(generated.keys())}),
    }


def _generate_artifact(*, artifact_type: str, state: UseCaseState) -> str:
    ucid = state.get("use_case_id", "unknown")
    cls = state.get("classification", {})
    payload = state.get("submission_payload", {})
    return (
        f"# {artifact_type}\n\n"
        f"## Use Case\n- ID: `{ucid}`\n\n"
        f"## Classification\n- {cls}\n\n"
        f"## Submission Snapshot\n- {payload}\n\n"
        f"## Generated Content\n"
        f"This is a dummy enterprise artifact generated by the orchestrator.\n"
    )


async def eval_check_node(state: UseCaseState, *, client: InternalApiClient) -> UseCaseState:
    # Ensure all required evaluations are present; trigger missing ones.
    policy = state.get("policy", {})
    required_evals = list(policy.get("required_evaluations", []))
    metrics = dict(state.get("eval_metrics", {}))

    missing_evals = [e for e in required_evals if _metric_key(e) not in metrics]
    if missing_evals:
        resp = await client.trigger_evaluations(
            use_case_id=_uuid(state["use_case_id"]), evaluations=missing_evals
        )
        metrics = resp.get("eval_metrics", metrics)
        eval_audit = _audit("EVAL_TRIGGERED", {"evaluations": missing_evals})
    else:
        eval_audit = []

    # Evaluate thresholds
    toxicity = float(metrics.get("toxicity", 0.0) or 0.0)
    if toxicity > 0.07:
        failed = {"reason": "toxicity", "value": toxicity}
        status_audit = _audit("EVAL_FAILED", {"toxicity": toxicity})
    else:
        failed = None
        status_audit = _audit("EVAL_OK", {"toxicity": toxicity})

    return {
        "eval_metrics": metrics,
        "eval_failed": failed,
        "audit_log": [*eval_audit, *status_audit],
    }


def _metric_key(eval_name: str) -> str:
    if eval_name == "TOXICITY":
        return "toxicity"
    if eval_name == "PROMPT_INJECTION":
        return "prompt_injection"
    if eval_name == "REDACTABILITY":
        return "redactability"
    return eval_name.lower()


async def approval_check_node(state: UseCaseState, *, client: InternalApiClient) -> UseCaseState:
    # Evaluate governance approval status and determine if any systems rejected.
    resp = await client.approval_status(use_case_id=_uuid(state["use_case_id"]))
    snapshot = _normalize_approval_snapshot(resp)

    rejected = [k for k, v in snapshot.items() if str(v.get("state")) == "REJECTED"]
    if rejected:
        approval_rejected = {"systems": rejected}
        audit = _audit("APPROVAL_REJECTED", {"systems": rejected})
    else:
        approval_rejected = None
        audit = _audit("APPROVAL_OK", {})

    return {"approval_status": snapshot, "approval_rejected": approval_rejected, "audit_log": audit}


async def remediation_node(state: UseCaseState) -> UseCaseState:
    # Decide corrective actions and increment remediation counter.
    attempts = int(state.get("remediation_attempts", 0) or 0) + 1

    # Dummy remediation: if eval failed toxicity, add a firewall rules artifact request
    missing = list(state.get("missing_artifacts", []))
    if state.get("eval_failed"):
        missing = list(dict.fromkeys([*missing, "AI_FIREWALL_RULES"]))
        audit = _audit(
            "REMEDIATION_PLANNED", {"attempt": attempts, "action": "add_ai_firewall_rules"}
        )
    else:
        audit = _audit("REMEDIATION_PLANNED", {"attempt": attempts, "action": "noop"})

    return {"remediation_attempts": attempts, "missing_artifacts": missing, "audit_log": audit}


async def escalation_node(state: UseCaseState, *, max_attempts: int) -> UseCaseState:
    # Trigger HITL interrupt for high risk or repeated failed remediation.
    risk = state.get("risk_level", "UNKNOWN")
    attempts = int(state.get("remediation_attempts", 0) or 0)
    if risk == "HIGH" or attempts >= max_attempts:
        payload = {
            "risk_level": risk,
            "remediation_attempts": attempts,
            "reason": "high_risk" if risk == "HIGH" else "max_attempts_exceeded",
            "approval_status": state.get("approval_status", {}),
            "eval_metrics": state.get("eval_metrics", {}),
        }
        # The exception is caught by the service layer which persists interrupt details.
        raise HumanInterrupt(reason="Human approval required", payload=payload)
    return {"audit_log": _audit("ESCALATION_SKIPPED", {"attempts": attempts, "risk_level": risk})}


def route_after_gap(state: UseCaseState) -> str:
    if state.get("missing_artifacts"):
        return "artifact_generation"
    return "eval_check"


def route_after_eval(state: UseCaseState) -> str:
    if state.get("eval_failed"):
        return "remediation"
    return "approval_check"


def route_after_approval(state: UseCaseState) -> str:
    if state.get("approval_rejected"):
        return "remediation"
    return "finish"


def route_after_remediation(state: UseCaseState) -> str:
    # If remediation created missing artifacts, go generate them; else re-run eval/approval.
    if state.get("missing_artifacts"):
        return "artifact_generation"
    return "eval_check"


def _uuid(v: str) -> uuid.UUID:
    import uuid as _uuid_mod

    return _uuid_mod.UUID(v)


def _lit(
    v: str,
) -> Literal["PCI", "NON_PCI", "UNKNOWN", "CLOUD", "ON_PREM", "INTERNAL", "EXTERNAL"]:
    # Type helper for InternalApiClient signature; runtime is just strings.
    return v  # type: ignore[return-value]


# --- Module Notes -----------------------------------------------------------
# Nodes should not perform DB writes directly; persistence is owned by the service layer.
# Tool calls are mediated through `InternalApiClient` to preserve a stable integration boundary.
