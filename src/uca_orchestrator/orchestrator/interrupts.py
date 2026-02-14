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
