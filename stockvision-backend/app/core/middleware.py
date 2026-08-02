"""
Cross-cutting HTTP middleware.

These are ASGI middlewares rather than FastAPI dependencies because they must
wrap responses (and failures) that never reach a route handler at all — a 404 on
an unknown path, or an unhandled exception — which a `Depends(...)` cannot see.
"""
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import request_id_ctx

logger = logging.getLogger("stockvision.access")

# Scraped/probed on a timer, so logging them buries real traffic.
_QUIET_PATHS = {"/metrics", "/health", "/health/live", "/health/ready", "/favicon.ico"}


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Assigns every request a correlation ID, publishes it to the logging
    ContextVar, echoes it back as `X-Request-ID`, and records wall-clock
    duration in `X-Response-Time-ms`.

    Honours an inbound `X-Request-ID` so a trace started at the edge (NGINX sets
    one — see deploy/nginx/nginx.conf) survives into application logs instead of
    being renumbered at the app boundary.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = request_id_ctx.set(request_id)
        request.state.request_id = request_id
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "Unhandled exception during %s %s after %.1fms",
                request.method, request.url.path, elapsed_ms,
                extra={"http_method": request.method, "http_path": request.url.path},
            )
            raise
        finally:
            request_id_ctx.reset(token)

        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-ms"] = f"{elapsed_ms:.1f}"

        if request.url.path not in _QUIET_PATHS:
            log = logger.info if response.status_code < 400 else logger.warning
            log(
                "%s %s -> %d (%.1fms)",
                request.method, request.url.path, response.status_code, elapsed_ms,
                extra={
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "http_status": response.status_code,
                    "duration_ms": round(elapsed_ms, 2),
                },
            )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Baseline security response headers.

    Security improvement: the API previously returned none of these. Even for a
    JSON API they matter — `X-Content-Type-Options: nosniff` stops a browser
    re-interpreting an API response as HTML (the mechanism behind a family of
    reflected-XSS-via-JSON bugs), and `Referrer-Policy` stops full URLs (which
    carry symbols and portfolio IDs in the path) leaking to third-party origins.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        return response
