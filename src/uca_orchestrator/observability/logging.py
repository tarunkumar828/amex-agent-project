"""
uca_orchestrator.observability.logging

Structured logging configuration for the service.

Responsibilities:
- Configure `structlog` for JSON logs suitable for ELK/Splunk/Datadog.
- Provide a small wrapper for obtaining bound loggers.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def configure_logging(*, service_name: str, level: str) -> None:
    """
    Structured JSON logs for ingestion in Splunk/ELK/Datadog.
    """

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )

    # structlog processors run on each log event; keep this list focused and stable.
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _add_service_name(service_name),
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def _add_service_name(service_name: str):
    # Adds a stable "service" field for log routing/aggregation across environments.
    def processor(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        event_dict.setdefault("service", service_name)
        return event_dict

    return processor


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


# --- Module Notes -----------------------------------------------------------
# Request-scoped metadata is bound via contextvars in `observability.middleware`.
