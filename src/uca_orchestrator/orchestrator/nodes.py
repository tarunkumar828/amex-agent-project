from __future__ import annotations

import asyncio
import uuid
from typing import Any, Literal

from uca_orchestrator.governance_clients.internal_http import InternalApiClient
from uca_orchestrator.orchestrator.interrupts import HumanInterrupt
from uca_orchestrator.orchestrator.state import UseCaseState


def _append_audit(state: UseCaseState, *, event: str, details: dict[str, Any]) -> None:
    audit = list(state.get("audit_log", []))
    audit.append({"event": event, "details": details})
    state["audit_log"] = audit


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

    state.setdefault("submission_payload", {})
    state.setdefault("classification", {})
    state.setdefault("missing_artifacts", [])
    state.setdefault("approval_status", {})
    state.setdefault("eval_metrics", {})
    state.setdefault("risk_level", "UNKNOWN")
    state.setdefault("remediation_attempts", 0)
    state.setdefault("escalation_required", False)
    state.setdefault("audit_log", [])

    _append_audit(state, event="ENTRY", details={})
    return state


async def classify_node(state: UseCaseState) -> UseCaseState:
    payload = state.get("submission_payload", {})

    data_classification = (payload.get("data_classification") or "UNKNOWN").upper()
    deployment_target = (payload.get("deployment_target") or "UNKNOWN").upper()
    model_provider = (payload.get("model_provider") or "UNKNOWN").upper()

    risk = "LOW"
    if data_classification == "PCI" or model_provider == "EXTERNAL":
        risk = "HIGH"
    elif deployment_target == "CLOUD":
        risk = "MEDIUM"

    state["classification"] = {
        "data_classification": data_classification,
        "deployment_target": deployment_target,
        "model_provider": model_provider,
    }
    state["risk_level"] = risk
    _append_audit(state, event="CLASSIFY", details={"risk_level": risk, **state["classification"]})
    return state


async def parallel_fetch_node(state: UseCaseState, *, client: InternalApiClient) -> UseCaseState:
    use_case_id = state["use_case_id"]

    cls = state.get("classification", {})
    data_classification = cls.get("data_classification", "UNKNOWN")
    deployment_target = cls.get("deployment_target", "UNKNOWN")
    model_provider = cls.get("model_provider", "UNKNOWN")

    reg_coro = client.registration_status(use_case_id=_uuid(use_case_id))
    policy_coro = client.policy_requirements(
        data_classification=_lit(data_classification),
        deployment_target=_lit(deployment_target),
        model_provider=_lit(model_provider),
    )
    approvals_coro = client.approval_status(use_case_id=_uuid(use_case_id))
    eval_coro = client.eval_status(use_case_id=_uuid(use_case_id))
    artifacts_coro = client.artifact_status(use_case_id=_uuid(use_case_id))

    reg, policy, approvals, evals, artifacts = await asyncio.gather(
        reg_coro, policy_coro, approvals_coro, eval_coro, artifacts_coro
    )

    state["submission_payload"] = reg.get("submission_payload", state.get("submission_payload", {}))
    state["approval_status"] = _normalize_approval_snapshot(approvals)
    state["eval_metrics"] = evals.get("eval_metrics", {})
    state["_policy"] = policy  # internal key (not in TypedDict on purpose)
    state["_artifact_types_present"] = list(artifacts.get("artifact_types", []))
    _append_audit(
        state,
        event="PARALLEL_FETCH",
        details={"policy": policy, "approvals": approvals, "evals": evals, "artifacts": artifacts},
    )
    return state


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
    policy = state.get("_policy", {})
    required = list(policy.get("required_artifacts", []))
    missing: list[str] = []

    present = set(state.get("_artifact_types_present", []))
    for a in required:
        if str(a) in present:
            continue
        missing.append(str(a))

    state["missing_artifacts"] = missing
    _append_audit(state, event="GAP_ANALYSIS", details={"required": required, "missing": missing})
    return state


async def artifact_generation_node(state: UseCaseState) -> UseCaseState:
    missing = list(state.get("missing_artifacts", []))
    generated = {}
    for art in missing:
        generated[art] = _generate_artifact(artifact_type=art, state=state)

    state["_generated_artifacts"] = generated
    state["missing_artifacts"] = []  # once generated, considered satisfied in dummy world
    _append_audit(state, event="ARTIFACT_GENERATION", details={"generated": list(generated.keys())})
    return state


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
    policy = state.get("_policy", {})
    required_evals = list(policy.get("required_evaluations", []))
    metrics = dict(state.get("eval_metrics", {}))

    missing_evals = [e for e in required_evals if _metric_key(e) not in metrics]
    if missing_evals:
        resp = await client.trigger_evaluations(
            use_case_id=_uuid(state["use_case_id"]), evaluations=missing_evals
        )
        metrics = resp.get("eval_metrics", metrics)
        state["eval_metrics"] = metrics
        _append_audit(
            state,
            event="EVAL_TRIGGERED",
            details={"evaluations": missing_evals, "metrics": metrics},
        )

    # Evaluate thresholds
    toxicity = float(metrics.get("toxicity", 0.0) or 0.0)
    if toxicity > 0.07:
        state["_eval_failed"] = {"reason": "toxicity", "value": toxicity}
        _append_audit(state, event="EVAL_FAILED", details={"toxicity": toxicity})
    else:
        state.pop("_eval_failed", None)
        _append_audit(state, event="EVAL_OK", details={"toxicity": toxicity})

    return state


def _metric_key(eval_name: str) -> str:
    if eval_name == "TOXICITY":
        return "toxicity"
    if eval_name == "PROMPT_INJECTION":
        return "prompt_injection"
    if eval_name == "REDACTABILITY":
        return "redactability"
    return eval_name.lower()


async def approval_check_node(state: UseCaseState, *, client: InternalApiClient) -> UseCaseState:
    resp = await client.approval_status(use_case_id=_uuid(state["use_case_id"]))
    snapshot = _normalize_approval_snapshot(resp)
    state["approval_status"] = snapshot

    rejected = [k for k, v in snapshot.items() if str(v.get("state")) == "REJECTED"]
    if rejected:
        state["_approval_rejected"] = {"systems": rejected}
        _append_audit(state, event="APPROVAL_REJECTED", details={"systems": rejected})
    else:
        state.pop("_approval_rejected", None)
        _append_audit(state, event="APPROVAL_OK", details={})
    return state


async def remediation_node(state: UseCaseState) -> UseCaseState:
    attempts = int(state.get("remediation_attempts", 0) or 0) + 1
    state["remediation_attempts"] = attempts

    # Dummy remediation: if eval failed toxicity, add a firewall rules artifact request
    if state.get("_eval_failed"):
        state["missing_artifacts"] = list(
            dict.fromkeys([*list(state.get("missing_artifacts", [])), "AI_FIREWALL_RULES"])
        )
        _append_audit(
            state,
            event="REMEDIATION_PLANNED",
            details={"attempt": attempts, "action": "add_ai_firewall_rules"},
        )
    else:
        _append_audit(
            state, event="REMEDIATION_PLANNED", details={"attempt": attempts, "action": "noop"}
        )
    return state


async def escalation_node(state: UseCaseState, *, max_attempts: int) -> UseCaseState:
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
        _append_audit(state, event="ESCALATION_REQUIRED", details=payload)
        raise HumanInterrupt(reason="Human approval required", payload=payload)
    return state


def route_after_gap(state: UseCaseState) -> str:
    if state.get("missing_artifacts"):
        return "artifact_generation"
    return "eval_check"


def route_after_eval(state: UseCaseState) -> str:
    if state.get("_eval_failed"):
        return "remediation"
    return "approval_check"


def route_after_approval(state: UseCaseState) -> str:
    if state.get("_approval_rejected"):
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
