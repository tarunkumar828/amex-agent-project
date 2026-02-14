"""
uca_orchestrator.api.__main__

Entrypoint for running the FastAPI application via `python -m uca_orchestrator.api`.

Responsibilities:
- Load settings.
- Create the app.
- Start uvicorn with structlog-compatible logging config.
"""

from __future__ import annotations

import uvicorn

from uca_orchestrator.api.app import create_app
from uca_orchestrator.settings import get_settings


def main() -> None:
    settings = get_settings()
    app = create_app(settings=settings)

    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_config=None,  # structlog
    )


if __name__ == "__main__":
    main()


# --- Module Notes -----------------------------------------------------------
# For production, this is commonly invoked behind a process manager (systemd/k8s)
# and fronted by an ingress/load balancer.
