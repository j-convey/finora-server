import logging
from typing import Any

import structlog

from app.core.config import settings


def get_logger(name: str = "finora") -> structlog.stdlib.BoundLogger:
    """Logger factory used everywhere in the app."""
    return structlog.get_logger(name)


def _add_global_context(logger: Any, method_name: str, event_dict: dict) -> dict:
    """Stamp every log line with deployment-level context."""
    event_dict["environment"] = settings.ENVIRONMENT
    event_dict["app_version"] = settings.APP_VERSION
    event_dict["git_commit"] = settings.GIT_COMMIT
    return event_dict


def setup_logging() -> None:
    """Call once in main.py. Single source of truth — reads from settings."""
    is_production = settings.ENVIRONMENT == "production"

    # Configure stdlib logging — required for structlog's stdlib bridge to work.
    logging.basicConfig(
        format="%(message)s",
        level=logging.INFO if is_production else logging.DEBUG,
        force=True,
    )

    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        _add_global_context,
        structlog.processors.ExceptionRenderer(),
    ]

    if is_production:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
