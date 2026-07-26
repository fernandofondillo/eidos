"""Logging estructurado para EIDOS.

Wrapper sobre structlog que admite formato JSON (producción) o
consola legible (desarrollo). Toda la base de código usa get_logger(__name__).
"""

from __future__ import annotations

import logging
import sys
from typing import Literal

import structlog


def configure_logging(
    level: str = "INFO",
    format: Literal["json", "console"] = "console",
) -> None:
    """Configura structlog una vez al arranque del proceso."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Devuelve un logger estructurado para el módulo dado."""
    return structlog.get_logger(name)


__all__ = ["configure_logging", "get_logger"]
