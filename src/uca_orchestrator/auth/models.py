"""
uca_orchestrator.auth.models

Auth domain models.

Responsibilities:
- Define the authenticated identity type (`Principal`) injected into endpoints.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Principal:
    """
    Authenticated caller identity.
    """

    subject: str
    roles: frozenset[str]

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles


# --- Module Notes -----------------------------------------------------------
# Keep this model minimal; it is used across API, services, and (optionally) tool boundaries.
