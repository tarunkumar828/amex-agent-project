from __future__ import annotations

import httpx
import pytest

from uca_orchestrator.api.app import create_app
from uca_orchestrator.settings import Settings


@pytest.mark.asyncio
async def test_health_endpoints() -> None:
    app = create_app(settings=Settings(env="test"))

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
