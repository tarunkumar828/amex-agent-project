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
            structlog.contextvars.clear_contextvars()

        response.headers["x-request-id"] = request_id
        return response
