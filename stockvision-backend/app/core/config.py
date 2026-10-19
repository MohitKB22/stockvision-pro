"""
Centralized application configuration.

pydantic-settings validates every value at process startup (fail fast) rather
than surfacing a KeyError deep inside a request handler. All values are
overridable via environment variables, which is what lets the same image run in
dev / staging / prod (12-factor).

CHANGE LOG (v2.0):
  - REMOVED JWT_SECRET_KEY / JWT_ALGORITHM / ACCESS_TOKEN_EXPIRE_MINUTES /
    REFRESH_TOKEN_EXPIRE_DAYS. There is no authentication any more, so a signing
    secret is dead configuration — and a dead secret with a
    "CHANGE_ME_IN_PRODUCTION" default is a real liability: it invites someone to
    wire auth back up against an unchanged key.
  - ADDED DEFAULT_MARKET, REPORT_STORAGE_DIR, MAX_UPLOAD_BYTES, LOG_LEVEL,
    LOG_FORMAT and CORS_ORIGINS parsing that tolerates a comma-separated string.
"""
import os
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.domain.enums import Market

# Vercel sets VERCEL=1 in every build and function; AWS Lambda sets the function
# name. On these platforms the deployment directory is read-only, instances are
# short-lived and many can run at once — several defaults below change because of it.
IS_SERVERLESS = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

# Vercel caps a function's request body at 4.5 MB; a larger upload is rejected by
# the platform before it reaches the app, with an HTML error instead of the API's
# JSON envelope. Keeping the app's own limit just under that means the client
# always gets a real, explainable error.
SERVERLESS_MAX_UPLOAD_BYTES = 4 * 1024 * 1024

# Connection-string names hosted Postgres integrations inject (Neon, Vercel
# Postgres, Supabase, Render, Heroku), tried in order when DATABASE_URL is unset.
_DATABASE_URL_FALLBACKS = ("POSTGRES_URL", "DATABASE_URL_UNPOOLED", "POSTGRES_URL_NON_POOLING")
# Query parameters some providers append for Prisma that libpq rejects outright.
_NON_LIBPQ_PARAMS = {"pgbouncer", "schema", "connection_limit", "pool_timeout"}


def normalize_database_url(url: str) -> str:
    """
    `postgres://...` -> `postgresql://...`, minus Prisma-only query parameters.

    SQLAlchemy 2 removed the `postgres://` alias, yet it is exactly what Vercel's
    Postgres integration, Heroku and Render hand out — so a copied connection
    string crashed the process at import with `NoSuchModuleError: postgres`.
    """
    url = (url or "").strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if not url.startswith("postgresql") or "?" not in url:
        return url
    base, _, query = url.partition("?")
    kept = [p for p in query.split("&") if p and p.split("=", 1)[0].lower() not in _NON_LIBPQ_PARAMS]
    return f"{base}?{'&'.join(kept)}" if kept else base


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App metadata -------------------------------------------------------
    APP_NAME: str = "StockVision Pro"
    APP_VERSION: str = "2.0.0"
    ENVIRONMENT: Literal["development", "staging", "production", "test"] = "development"
    API_V1_PREFIX: str = "/api/v1"

    # --- Markets ------------------------------------------------------------
    # Which market the API assumes when a request doesn't specify one. The UI
    # always sends an explicit `market`, so this only affects direct API use.
    DEFAULT_MARKET: Market = Market.INDIA

    # --- Database -----------------------------------------------------------
    # Production target is PostgreSQL (see docker-compose.yml + migrations/).
    # Defaults to a local SQLite file so the project runs with zero external
    # services for development and demo.
    DATABASE_URL: str = "sqlite:///./stockvision.db"
    # Serverless instances are many and short-lived, so each keeps few idle
    # connections — but one instance still serves a page's burst of concurrent
    # calls (the dashboard issues ~12 at once, and every request opens a second
    # session for its audit entry). A cap of 5 queued those for 30 s until the
    # browser gave up; 20 per instance is comfortable through a pooled endpoint
    # such as Neon's `-pooler` host, which is what DATABASE_URL should point to.
    DB_POOL_SIZE: int = 5 if IS_SERVERLESS else 10
    DB_MAX_OVERFLOW: int = 15 if IS_SERVERLESS else 20
    # Fail fast instead of hanging a request for SQLAlchemy's default 30 s.
    DB_POOL_TIMEOUT: int = 10
    DB_ECHO: bool = False

    # --- Redis / Celery -----------------------------------------------------
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    CACHE_TTL_SECONDS: int = 30

    # --- Rate limiting ------------------------------------------------------
    RATE_LIMIT_PER_MINUTE: int = 600
    RATE_LIMIT_ENABLED: bool = True

    # --- Observability ------------------------------------------------------
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    LOG_FORMAT: Literal["json", "console"] = "console"

    # Prometheus `/metrics`. On serverless each instance has its own short-lived
    # counters and nothing scrapes them, so the endpoint is noise there.
    METRICS_ENABLED: bool = not IS_SERVERLESS

    # --- CORS ---------------------------------------------------------------
    # NoDecode: without it pydantic-settings JSON-decodes list fields read from
    # the ENVIRONMENT before any validator runs, so `CORS_ORIGINS=https://a.com`
    # (or `a.com,b.com`) raised SettingsError and the process died at import. The
    # validator below always handled the comma-separated form — it just never
    # got the chance for values that came from real environment variables.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    # Optional regex for origins that cannot be listed in advance, e.g. a hosting
    # provider's per-deployment preview URLs:  ^https://stockvision-pro.*\.vercel\.app$
    CORS_ORIGIN_REGEX: str | None = None

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        """
        Accept `CORS_ORIGINS=http://a.com,http://b.com` from the environment.

        Bug fixed: pydantic-settings parses complex types (list/dict) as JSON
        first, so the natural comma-separated form that every deployment tool
        produces raised `SettingsError: error parsing value for field` and killed
        the process at boot. Accepting both forms removes an entire class of
        "works locally, crashes in Docker" incident.
        """
        if isinstance(v, str):
            s = v.strip()
            if s.startswith("["):
                import json

                return json.loads(s)
            return [origin.strip() for origin in s.split(",") if origin.strip()]
        return v

    # --- ML -----------------------------------------------------------------
    MODEL_ARTIFACT_DIR: str = "./ml_artifacts"
    OPTUNA_N_TRIALS: int = 20
    # Ceilings on one synchronous training request. A serverless function has a
    # hard time limit (300 s on Vercel's free plan) and a monthly CPU allowance,
    # so the request schema's own maxima (200 trials x 20 folds) would simply be
    # killed mid-run there; the API now says so up front instead.
    ML_MAX_OPTUNA_TRIALS: int = 40 if IS_SERVERLESS else 200
    ML_MAX_WALK_FORWARD_SPLITS: int = 8 if IS_SERVERLESS else 20

    # --- File storage -------------------------------------------------------
    # Where model artifacts, generated reports and uploaded PDFs are kept.
    #   filesystem: the three *_DIR settings below (Docker volumes, local dev)
    #   database:   a `stored_files` table — for hosts whose disk is read-only or
    #               wiped between instances (Vercel and other serverless)
    STORAGE_BACKEND: Literal["filesystem", "database"] = "database" if IS_SERVERLESS else "filesystem"
    # Optional cap on the bytes the database backend may hold (0 = unlimited).
    # Protects a free-tier database from being filled by a public deployment.
    STORAGE_QUOTA_BYTES: int = 0
    # Keep only the newest N generated reports (0 = keep everything).
    REPORT_RETENTION_COUNT: int = 0

    # --- RAG Copilot --------------------------------------------------------
    DOCUMENT_STORAGE_DIR: str = "./document_storage"
    REPORT_STORAGE_DIR: str = "./report_storage"
    MAX_UPLOAD_BYTES: int = SERVERLESS_MAX_UPLOAD_BYTES if IS_SERVERLESS else 25 * 1024 * 1024
    # 4096, not scikit-learn's ~2**20 default nor a smaller round number like
    # 512: empirically calibrated (see app/services/rag_service.py's
    # MIN_RELEVANCE_SCORE docstring). At 512 dimensions, hash collisions made
    # genuinely off-topic queries occasionally score HIGHER than genuinely
    # relevant ones (0.21 vs 0.25), so no threshold could separate them. 4096
    # pushes collision noise to ~0.055 while relevant matches stay ~0.20+.
    RAG_EMBEDDING_DIMENSION: int = 4096

    # --- External providers (optional; features degrade gracefully) ----------
    ALPHA_VANTAGE_API_KEY: str | None = None
    POLYGON_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None

    # --- Privacy ------------------------------------------------------------
    # The admin page lists recent API calls with the caller's IP. On a public
    # deployment that would publish every visitor's address, so by default the
    # address is truncated (IPv4 /24, IPv6 /48) before it is stored.
    AUDIT_ANONYMIZE_IP: bool = True

    @model_validator(mode="before")
    @classmethod
    def _database_url_fallbacks(cls, data: object) -> object:
        """Use the connection string a hosting integration injected when
        DATABASE_URL itself was not set."""
        if not isinstance(data, dict):
            return data
        if any(k.lower() == "database_url" and str(v or "").strip() for k, v in data.items()):
            return data
        for name in _DATABASE_URL_FALLBACKS:
            value = os.environ.get(name, "").strip()
            if value:
                return {**data, "DATABASE_URL": value}
        return data

    @field_validator("DATABASE_URL")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        return normalize_database_url(v)

    @model_validator(mode="after")
    def _serverless_limits(self) -> "Settings":
        """A serverless platform's own request-size ceiling wins over any
        larger configured upload limit."""
        if IS_SERVERLESS:
            self.MAX_UPLOAD_BYTES = min(self.MAX_UPLOAD_BYTES, SERVERLESS_MAX_UPLOAD_BYTES)
        return self

    @property
    def is_serverless(self) -> bool:
        return IS_SERVERLESS

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — avoids re-parsing env on every import."""
    return Settings()


settings = get_settings()
