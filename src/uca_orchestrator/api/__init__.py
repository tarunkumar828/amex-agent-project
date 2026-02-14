"""
uca_orchestrator.api

API package for the UCA Orchestrator service.

Responsibilities:
- FastAPI app factory and router modules.
- API-layer dependency wiring and request/response models.
"""

# Package marker.


# --- Module Notes -----------------------------------------------------------
# The API layer should remain thin: request validation + auth + delegation to services.
