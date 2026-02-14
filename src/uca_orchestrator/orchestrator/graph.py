from __future__ import annotations

from collections.abc import Awaitable, Callable

from uca_orchestrator.governance_clients.internal_http import InternalApiClient
from uca_orchestrator.orchestrator.nodes import (
    approval_check_node,
    artifact_generation_node,
    classify_node,
    entry_node,
    escalation_node,
    eval_check_node,
    gap_analysis_node,
    parallel_fetch_node,
    remediation_node,
    route_after_approval,
    route_after_eval,
    route_after_gap,
    route_after_remediation,
)
from uca_orchestrator.orchestrator.state import UseCaseState


def build_graph(*, client: InternalApiClient, max_attempts: int):
    """
    Returns a compiled LangGraph runnable.
    """

    try:
        from langgraph.graph import END, StateGraph  # type: ignore[import-not-found]
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "LangGraph is not available. Install dependencies (see requirements.txt)."
        ) from e

    graph = StateGraph(UseCaseState)

    graph.add_node("entry", entry_node)
    graph.add_node("classify", classify_node)
    graph.add_node("parallel_fetch", _bind_client(parallel_fetch_node, client))
    graph.add_node("gap_analysis", gap_analysis_node)
    graph.add_node("artifact_generation", artifact_generation_node)
    graph.add_node("eval_check", _bind_client(eval_check_node, client))
    graph.add_node("approval_check", _bind_client(approval_check_node, client))
    graph.add_node("remediation", remediation_node)
    graph.add_node("escalation", _bind_max_attempts(escalation_node, max_attempts))
    graph.add_node("finish", _finish_node)

    graph.set_entry_point("entry")

    graph.add_edge("entry", "classify")
    graph.add_edge("classify", "parallel_fetch")
    graph.add_edge("parallel_fetch", "gap_analysis")

    graph.add_conditional_edges(
        "gap_analysis",
        route_after_gap,
        {"artifact_generation": "artifact_generation", "eval_check": "eval_check"},
    )
    graph.add_edge("artifact_generation", "eval_check")

    graph.add_conditional_edges(
        "eval_check",
        route_after_eval,
        {"remediation": "remediation", "approval_check": "approval_check"},
    )
    graph.add_conditional_edges(
        "approval_check",
        route_after_approval,
        {"remediation": "remediation", "finish": "finish"},
    )

    graph.add_edge("remediation", "escalation")
    graph.add_conditional_edges(
        "escalation",
        route_after_remediation,
        {"artifact_generation": "artifact_generation", "eval_check": "eval_check"},
    )

    graph.add_edge("finish", END)

    return graph.compile()


def _bind_client(
    fn: Callable[..., Awaitable[UseCaseState]],
    client: InternalApiClient,
) -> Callable[[UseCaseState], Awaitable[UseCaseState]]:
    async def _wrapped(state: UseCaseState) -> UseCaseState:
        return await fn(state, client=client)

    return _wrapped


def _bind_max_attempts(
    fn: Callable[..., Awaitable[UseCaseState]],
    max_attempts: int,
) -> Callable[[UseCaseState], Awaitable[UseCaseState]]:
    async def _wrapped(state: UseCaseState) -> UseCaseState:
        return await fn(state, max_attempts=max_attempts)

    return _wrapped


async def _finish_node(state: UseCaseState) -> UseCaseState:
    audit = list(state.get("audit_log", []))
    audit.append({"event": "FINISH", "details": {"status": "APPROVAL_READY"}})
    state["audit_log"] = audit
    state["escalation_required"] = False
    return state
