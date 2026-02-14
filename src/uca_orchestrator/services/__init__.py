"""
uca_orchestrator.services

Service-layer package.

Responsibilities:
- Own transaction boundaries and persistence decisions.
- Orchestrate calls across DB, orchestrator, and tool clients.
"""

# Package marker.


# --- Module Notes -----------------------------------------------------------
# Services should be pure Python and easily testable with fake clients/sessions.
