"""
uca_orchestrator.api.app

FastAPI app factory for the UCA Orchestrator service.

Responsibilities:
- Build the FastAPI application and register routers/middleware.
- Initialize and dispose shared infrastructure (DB engine/session factory).
- Provide a single composition root where cross-cutting concerns live.
"""

from __future__ import annotations

from fastapi import FastAPI

from uca_orchestrator.api.routers.dev_auth import router as dev_auth_router
from uca_orchestrator.api.routers.health import router as health_router
from uca_orchestrator.api.routers.internal.router import router as internal_router
from uca_orchestrator.api.routers.runs import router as runs_router
from uca_orchestrator.api.routers.use_cases import router as use_cases_router
from uca_orchestrator.db.init_db import init_db
from uca_orchestrator.db.session import create_engine, create_sessionmaker
from uca_orchestrator.observability.logging import configure_logging, get_logger
from uca_orchestrator.observability.middleware import RequestContextMiddleware
from uca_orchestrator.settings import Settings

log = get_logger(__name__)


def create_app(*, settings: Settings) -> FastAPI:
    # Configure structured logging once at process startup (before app serves requests).
    configure_logging(service_name=settings.service_name, level=settings.log_level)

    app = FastAPI(
        title="Use Case Approval Orchestrator Agent",
        version="0.1.0",
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.add_middleware(RequestContextMiddleware)
    app.include_router(health_router, tags=["health"])
    app.include_router(dev_auth_router)
    app.include_router(internal_router)
    app.include_router(use_cases_router)
    app.include_router(runs_router)

    @app.on_event("startup")
    async def _startup() -> None:
        log.info("startup", env=settings.env)
        # Create the async DB engine and session factory once and stash them on app.state.
        # Routers obtain sessions via dependencies (see `uca_orchestrator.api.deps`).
        engine = create_engine(settings)
        app.state.engine = engine
        app.state.sessionmaker = create_sessionmaker(engine)
        if settings.env in ("dev", "test"):
            # Dev/test convenience: create tables automatically. Prod should use Alembic migrations.
            await init_db(engine)

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        # Dispose the engine to close pools/FDs gracefully.
        engine = getattr(app.state, "engine", None)
        if engine is not None:
            await engine.dispose()
        log.info("shutdown")

    return app


# --- Module Notes -----------------------------------------------------------
# This file is intentionally small: app composition stays here; business logic stays
# in routers/services/orchestrator layers.
