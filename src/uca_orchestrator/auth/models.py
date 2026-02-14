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
