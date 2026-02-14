"""
uca_orchestrator.db

Persistence package (SQLAlchemy async).

Responsibilities:
- Provide ORM models, engine/session setup, and repositories.
"""

# Package marker.


# --- Module Notes -----------------------------------------------------------
# This package is designed to be replaceable (e.g., switching DB backends) without
# rewriting orchestrator or service logic.
