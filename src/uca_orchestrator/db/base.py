"""
uca_orchestrator.db.base

SQLAlchemy declarative base.

Responsibilities:
- Provide a shared DeclarativeBase for all ORM models.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# --- Module Notes -----------------------------------------------------------
# All ORM models should inherit from `Base` so Alembic and metadata discovery work.
