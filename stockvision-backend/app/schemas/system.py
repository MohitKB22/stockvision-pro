from pydantic import BaseModel, Field


class AppSettings(BaseModel):
    """
    Server-persisted application preferences. Every field has a default in
    app/services/settings_service.py, so a GET always returns a complete object
    and the UI never has to handle partial settings.
    """
    theme: str = Field(default="dark", pattern="^(dark|midnight|system)$")
    language: str = Field(default="en", max_length=8)
    default_market: str = Field(default="IN", pattern="^(IN|US)$")
    default_dashboard: str = Field(default="dashboard", max_length=32)
    number_format: str = Field(default="auto", pattern="^(auto|indian|western)$")
    email_notifications: bool = True
    push_notifications: bool = True
    market_alerts: bool = True
    signal_alerts: bool = True
    price_alerts: bool = True
    weekly_digest: bool = False
    chart_type: str = Field(default="area", pattern="^(area|line|candlestick)$")
    auto_refresh_seconds: int = Field(default=30, ge=0, le=600)
    reduced_motion: bool = False


class AppSettingsUpdate(BaseModel):
    """Partial update — unknown keys are dropped by the service, not persisted."""
    theme: str | None = Field(default=None, pattern="^(dark|midnight|system)$")
    language: str | None = Field(default=None, max_length=8)
    default_market: str | None = Field(default=None, pattern="^(IN|US)$")
    default_dashboard: str | None = Field(default=None, max_length=32)
    number_format: str | None = Field(default=None, pattern="^(auto|indian|western)$")
    email_notifications: bool | None = None
    push_notifications: bool | None = None
    market_alerts: bool | None = None
    signal_alerts: bool | None = None
    price_alerts: bool | None = None
    weekly_digest: bool | None = None
    chart_type: str | None = Field(default=None, pattern="^(area|line|candlestick)$")
    auto_refresh_seconds: int | None = Field(default=None, ge=0, le=600)
    reduced_motion: bool | None = None


class ApiKeyStatus(BaseModel):
    """
    Whether an integration is configured — never the key itself.

    Security: the Settings page shows connection status only. Returning a masked
    key still leaks length and prefix, and returning the real value over an
    unauthenticated API would be indefensible. Keys are set via environment
    variables and are never readable through HTTP.
    """
    provider: str
    label: str
    configured: bool
    description: str
