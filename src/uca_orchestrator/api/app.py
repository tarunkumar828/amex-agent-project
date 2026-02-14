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
        engine = create_engine(settings)
        app.state.engine = engine
        app.state.sessionmaker = create_sessionmaker(engine)
        if settings.env in ("dev", "test"):
            await init_db(engine)

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        engine = getattr(app.state, "engine", None)
        if engine is not None:
            await engine.dispose()
        log.info("shutdown")

    return app
