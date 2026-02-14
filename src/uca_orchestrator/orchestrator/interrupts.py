"""
uca_orchestrator.orchestrator.interrupts

Domain-specific exceptions used by the orchestration graph.

Responsibilities:
- Signal an explicit "human-in-the-loop" interrupt with structured payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class HumanInterrupt(Exception):
    """
    Raised by the graph when a human decision is required.
    The API layer persists the payload and exposes a resume endpoint.
    """

    reason: str
    payload: dict[str, Any]


# --- Module Notes -----------------------------------------------------------
# The service layer catches this exception, persists interrupt payload, and exposes
# a resume endpoint to merge a human decision back into state.
