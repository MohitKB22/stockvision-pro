"""Application settings and integration-status endpoints — new in v2.0."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings as app_config
from app.core.database import get_db
from app.schemas.system import ApiKeyStatus, AppSettings, AppSettingsUpdate
from app.services.settings_service import SettingsService

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("", response_model=AppSettings, summary="Application preferences")
def get_settings(db: Session = Depends(get_db)):
    """Always returns a complete object — stored values merged over defaults."""
    return SettingsService(db).get()


@router.patch("", response_model=AppSettings, summary="Update preferences")
def update_settings(payload: AppSettingsUpdate, db: Session = Depends(get_db)):
    return SettingsService(db).update(payload.model_dump(exclude_none=True))


@router.post("/reset", response_model=AppSettings, summary="Restore defaults")
def reset_settings(db: Session = Depends(get_db)):
    return SettingsService(db).reset()


@router.get("/integrations", response_model=list[ApiKeyStatus], summary="Integration status")
def integration_status():
    """
    Reports whether each integration is configured — never the key itself.

    Security: even a masked key leaks length and prefix. Keys are supplied via
    environment variables and are not readable through this API at all.
    """
    return [
        ApiKeyStatus(
            provider="openai", label="OpenAI",
            configured=bool(app_config.OPENAI_API_KEY),
            description="Powers the AI Copilot's generated answers. Without it the copilot uses the extractive fallback engine.",
        ),
        ApiKeyStatus(
            provider="gemini", label="Google Gemini",
            configured=bool(app_config.GEMINI_API_KEY),
            description="Alternative LLM backend for the Copilot, used when no OpenAI key is present.",
        ),
        ApiKeyStatus(
            provider="alpha_vantage", label="Alpha Vantage",
            configured=bool(app_config.ALPHA_VANTAGE_API_KEY),
            description="Live daily price refresh via the scheduled Celery task.",
        ),
        ApiKeyStatus(
            provider="polygon", label="Polygon.io",
            configured=bool(app_config.POLYGON_API_KEY),
            description="Alternative market-data provider for the price refresh task.",
        ),
    ]
