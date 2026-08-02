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
from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.enums import Market


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
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
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

    # --- CORS ---------------------------------------------------------------
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

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
                return v
            return [origin.strip() for origin in s.split(",") if origin.strip()]
        return v

    # --- ML -----------------------------------------------------------------
    MODEL_ARTIFACT_DIR: str = "./ml_artifacts"
    OPTUNA_N_TRIALS: int = 20

    # --- RAG Copilot --------------------------------------------------------
    DOCUMENT_STORAGE_DIR: str = "./document_storage"
    REPORT_STORAGE_DIR: str = "./report_storage"
    MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024  # hard ceiling on PDF uploads
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
