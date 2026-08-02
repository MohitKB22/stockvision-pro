"""
FastAPI application entrypoint.

CHANGE LOG (v2.0):
  - The entire authentication subsystem is gone. There is no login, no JWT, no
    session and no protected route: the API is open and the SPA opens directly on
    the dashboard.
  - Exception handling is now uniform across FOUR classes of failure, not one.
    Previously only `AppException` was handled, so a Pydantic validation error
    returned FastAPI's default `{"detail": [...]}` shape while a domain error
    returned `{"detail": "..."}` — two incompatible shapes the frontend had to
    special-case. Everything now returns the same `{"error": {...}}` envelope
    with a stable `code`.
  - Unhandled exceptions no longer leak a stack trace or internal message to the
    client. They are logged in full with the request ID; the response carries
    only that ID. (Security: the previous behaviour surfaced internal paths and
    SQL fragments to anyone who could trigger a 500.)
  - Every API request is recorded as telemetry, which is what makes the admin
    dashboard's analytics real measurements rather than decoration.
"""
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.dependencies import rate_limiter
from app.core.exceptions import AppException
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.core.monitoring import setup_prometheus, setup_tracing
from app.domain.enums import AuditAction
from app.schemas.common import ErrorEnvelope, HealthResponse

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: ensure storage directories exist, and create tables on SQLite.

    PostgreSQL deployments must run `alembic upgrade head` — `create_all()` only
    ever creates MISSING tables, it cannot apply schema *changes* to an existing
    database, which is exactly the gap versioned migrations cover. Auto-creating
    in production would silently mask a forgotten migration.
    """
    for directory in (
        settings.DOCUMENT_STORAGE_DIR, settings.MODEL_ARTIFACT_DIR, settings.REPORT_STORAGE_DIR
    ):
        Path(directory).mkdir(parents=True, exist_ok=True)

    if settings.is_sqlite:
        logger.info("SQLite backend detected — auto-creating tables for local/dev convenience.")
        Base.metadata.create_all(bind=engine)
    else:
        logger.info("PostgreSQL backend detected — assuming `alembic upgrade head` has been run.")

    logger.info("%s v%s starting in %s mode", settings.APP_NAME, settings.APP_VERSION, settings.ENVIRONMENT)
    yield
    logger.info("%s shutting down", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "AI-powered stock market analytics platform — market intelligence, portfolio "
        "analytics, risk engine, ML prediction and a RAG copilot over financial documents.\n\n"
        "**This API is unauthenticated by design.** It is intended to run behind a private "
        "network boundary or a reverse proxy that terminates access control; do not expose "
        "it directly to the public internet."
    ),
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    responses={
        400: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope}, 429: {"model": ErrorEnvelope},
        500: {"model": ErrorEnvelope},
    },
)

# Middleware order is significant — Starlette applies these outermost-last, so
# RequestContextMiddleware (added last) wraps everything and therefore sees and
# logs failures raised inside every other layer.
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,  # no cookies, no auth headers — nothing to send credentials for
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-Response-Time-ms"],
    max_age=3600,
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)

setup_prometheus(app)   # exposes GET /metrics
setup_tracing(app)      # OpenTelemetry auto-instrumentation


# --- Error handling ---------------------------------------------------------
def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """Domain exceptions — the expected, meaningful failures."""
    if exc.status_code >= 500:
        logger.error("Domain error %s: %s", exc.code, exc.detail, exc_info=True)
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload(_request_id(request)))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Pydantic validation failures, reshaped into the standard envelope.

    Field errors are preserved in `context.fields` so a form can highlight the
    exact input that failed — previously the frontend received FastAPI's own
    nested list shape and could only show a generic message.
    """
    fields = [
        {
            "field": ".".join(str(part) for part in error.get("loc", ()) if part != "body"),
            "message": error.get("msg", "Invalid value"),
            "type": error.get("type", "value_error"),
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "One or more fields failed validation.",
                "status": 422,
                "context": {"fields": fields},
                "request_id": _request_id(request),
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Framework-raised HTTP errors (404 on an unknown path, 405, ...)."""
    codes = {404: "not_found", 405: "method_not_allowed", 400: "bad_request", 403: "forbidden"}
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": codes.get(exc.status_code, "http_error"),
                "message": str(exc.detail),
                "status": exc.status_code,
                "request_id": _request_id(request),
            }
        },
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    The safety net.

    Security: the client receives a generic message and the request ID only. The
    full traceback goes to the logs, where it belongs — returning it in the
    response body (the previous behaviour for anything that was not an
    AppException) leaks file paths, dependency versions and sometimes SQL.
    """
    request_id = _request_id(request)
    logger.exception(
        "Unhandled exception on %s %s [request_id=%s]", request.method, request.url.path, request_id
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred. Quote the request ID when reporting this.",
                "status": 500,
                "request_id": request_id,
            }
        },
    )


# --- Telemetry --------------------------------------------------------------
# Paths excluded from audit telemetry: high-frequency polling and static concerns
# would otherwise dominate the table and the admin charts.
_UNAUDITED = {
    "/metrics", "/health", "/health/live", "/health/ready",
    "/docs", "/redoc", "/openapi.json", "/favicon.ico",
}


@app.middleware("http")
async def audit_api_calls(request: Request, call_next):
    """
    Records every API request in `audit_logs`.

    This is what makes the admin dashboard's API-volume, latency and error-rate
    figures real measurements rather than decoration. Writes happen on a separate
    short-lived session so an audit failure can never poison the request's own
    transaction, and the whole block is defensive — telemetry must never take
    down the endpoint it is measuring.
    """
    started = time.perf_counter()
    response = await call_next(request)

    path = request.url.path
    if path in _UNAUDITED or not path.startswith(settings.API_V1_PREFIX):
        return response

    try:
        from app.services.audit_service import AuditService

        db = SessionLocal()
        try:
            forwarded = request.headers.get("X-Forwarded-For")
            AuditService(db).log(
                action=AuditAction.API_CALL,
                resource=f"{request.method} {path}",
                detail={"query": str(request.url.query)[:500]} if request.url.query else {},
                ip_address=(
                    forwarded.split(",")[0].strip() if forwarded
                    else (request.client.host if request.client else None)
                ),
                status_code=response.status_code,
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        finally:
            db.close()
    except Exception:
        logger.debug("API-call telemetry write failed", exc_info=True)

    return response


# --- System routes ------------------------------------------------------------
@app.get("/health", response_model=HealthResponse, tags=["System"], summary="Liveness probe")
def health_check():
    return HealthResponse(
        status="ok",
        environment=settings.ENVIRONMENT,
        version=settings.APP_VERSION,
        database="sqlite" if settings.is_sqlite else "postgresql",
    )


@app.get("/health/ready", tags=["System"], summary="Readiness probe")
def readiness_check():
    """
    Distinct from /health on purpose: liveness answers "is the process alive",
    readiness answers "can it actually serve traffic". An orchestrator that
    conflates the two will keep routing requests to a replica whose database
    connection is broken.
    """
    from sqlalchemy import select

    db = SessionLocal()
    try:
        db.execute(select(1))
        return {"status": "ready", "database": "connected"}
    except Exception as exc:
        logger.error("Readiness probe failed: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"error": {"code": "not_ready", "message": "Database unreachable.", "status": 503}},
        )
    finally:
        db.close()


@app.get("/", tags=["System"], include_in_schema=False)
def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "api": settings.API_V1_PREFIX,
    }


app.include_router(api_router, prefix=settings.API_V1_PREFIX, dependencies=[Depends(rate_limiter)])
