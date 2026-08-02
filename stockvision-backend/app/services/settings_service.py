"""
Application Settings Service — new in v2.0.

Backs the Settings page. Preferences live server-side (in `app_settings`) rather
than in browser storage so they survive a cache clear and are shared across
devices — and because the reference design's Settings page presents them as
application configuration, not browser state.

Defaults are declared here in one place; a GET always returns a fully populated
object (defaults merged under whatever is stored), so the UI never has to handle
a half-missing settings payload.
"""
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings as app_config
from app.domain.enums import Market
from app.repositories.system_repository import SettingsRepository
from app.schemas.system import AppSettings

DEFAULTS: dict[str, Any] = {
    "theme": "dark",
    "language": "en",
    "default_market": app_config.DEFAULT_MARKET.value,
    "default_dashboard": "dashboard",
    "number_format": "auto",
    "email_notifications": True,
    "push_notifications": True,
    "market_alerts": True,
    "signal_alerts": True,
    "price_alerts": True,
    "weekly_digest": False,
    "chart_type": "area",
    "auto_refresh_seconds": 30,
    "reduced_motion": False,
}

_SETTINGS_KEY = "application"


class SettingsService:
    def __init__(self, db: Session) -> None:
        self.repo = SettingsRepository(db)

    def get(self) -> AppSettings:
        stored = self.repo.get_all().get(_SETTINGS_KEY, {})
        return AppSettings(**{**DEFAULTS, **(stored or {})})

    def update(self, patch: dict[str, Any]) -> AppSettings:
        """
        Partial update. Unknown keys are DROPPED rather than persisted —
        otherwise a typo in a client payload silently accumulates junk in the
        settings blob forever, and `AppSettings(**merged)` eventually starts
        failing validation for reasons nobody can trace.
        """
        stored = self.repo.get_all().get(_SETTINGS_KEY, {}) or {}
        clean = {k: v for k, v in patch.items() if k in DEFAULTS and v is not None}
        merged = {**DEFAULTS, **stored, **clean}
        self.repo.upsert(_SETTINGS_KEY, merged)
        return AppSettings(**merged)

    def reset(self) -> AppSettings:
        self.repo.upsert(_SETTINGS_KEY, dict(DEFAULTS))
        return AppSettings(**DEFAULTS)

    @property
    def default_market(self) -> Market:
        return Market(self.get().default_market)
