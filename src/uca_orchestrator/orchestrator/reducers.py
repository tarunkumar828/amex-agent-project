"""
uca_orchestrator.orchestrator.reducers

Reducers define how LangGraph merges concurrent/partial state updates.

Why reducers:
- When the graph runs true fan-out/fan-in, multiple nodes may update the same key.
- Reducers provide deterministic merge behavior (append, dict-merge, etc.).
"""

from __future__ import annotations

from typing import Any


def append_audit(
    left: list[dict[str, Any]] | None, right: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """
    Append-only reducer for audit log entries.

    Nodes should return `{"audit_log": [event]}` and this reducer will concatenate safely.
    """

    if not left:
        return list(right or [])
    if not right:
        return list(left)
    return [*left, *right]


def merge_dicts(
    left: dict[str, Any] | None, right: dict[str, Any] | None
) -> dict[str, Any]:
    """
    Shallow dict merge reducer (right wins on key collision).

    Useful for snapshot dictionaries like classification/metrics/approval_status where updates
    may be partial and arrive from multiple nodes.
    """

    if not left:
        return dict(right or {})
    if not right:
        return dict(left)
    return {**left, **right}

