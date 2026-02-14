"""
tests.test_smoke

Minimal smoke tests to validate the service can boot and serve core endpoints.

Responsibilities:
- Ensure the FastAPI app starts and DB readiness probe works in test mode.
"""

from __future__ import annotations

import httpx
import pytest

from uca_orchestrator.api.app import create_app
from uca_orchestrator.settings import Settings


@pytest.mark.asyncio
async def test_health_endpoints() -> None:
    app = create_app(settings=Settings(env="test"))

    # httpx 0.28 ASGITransport does not manage lifespan automatically; do it explicitly.
    await app.router.startup()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/healthz")
            assert r.status_code == 200
            assert r.json()["status"] == "ok"

            r = await client.get("/readyz")
            assert r.status_code == 200
            assert r.json()["status"] == "ready"
    finally:
        await app.router.shutdown()


# --- Module Notes -----------------------------------------------------------
# Add higher-level integration tests once orchestration endpoints are exercised with real fixtures.
