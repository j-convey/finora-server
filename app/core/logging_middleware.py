import structlog.contextvars
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from .logging import get_logger

logger = get_logger("finora.middleware")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        structlog.contextvars.clear_contextvars()

        # Prefer values set on request.state by auth middleware; fall back to headers.
        user_id = getattr(request.state, "user_id", None) or request.headers.get("X-User-ID")
        household_id = getattr(request.state, "household_id", None) or request.headers.get("X-Household-ID")

        is_demo_mode = request.headers.get("X-Demo-Mode", "").lower() == "true"
        structlog.contextvars.bind_contextvars(
            request_id=request.headers.get("X-Request-ID", "unknown"),
            user_id=user_id,
            household_id=household_id,
            path=str(request.url.path),
            method=request.method,
            demo_mode=is_demo_mode,
        )

        try:
            response = await call_next(request)
            logger.info("request completed", status_code=response.status_code)
            return response
        except Exception:
            logger.exception("request failed")
            raise
        finally:
            structlog.contextvars.clear_contextvars()
