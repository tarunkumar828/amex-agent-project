"""
uca_orchestrator.observability.middleware

HTTP middleware for request-scoped logging context.

Responsibilities:
- Generate/propagate request IDs.
- Bind request metadata into structlog contextvars.
"""

from __future__ import annotations

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    - Ensures every request has a request id
    - Binds request-scoped contextvars for structured logs
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Prefer a caller-provided request id for trace continuity; otherwise generate one.
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=request.url.path,
            method=request.method,
        )
        try:
            response: Response = await call_next(request)
        finally:
            # Avoid leaking context across requests under async concurrency.
            structlog.contextvars.clear_contextvars()

        response.headers["x-request-id"] = request_id
        return response


# --- Module Notes -----------------------------------------------------------
# This middleware complements `observability.logging.configure_logging` by ensuring
# request metadata is present on every log line without explicit parameter threading.
