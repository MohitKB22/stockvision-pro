"""
Domain-level enums — the shared vocabulary both the persistence layer
(app/models, SQLAlchemy) and the API layer (app/schemas, Pydantic) import.

CHANGE LOG (v2.0):
  - REMOVED `UserRole`. The platform no longer has accounts, authentication or
    role-based access control, so a role vocabulary has no referent. Every RBAC
    guard that consumed it was deleted alongside it.
  - REMOVED the LOGIN / LOGIN_FAILED audit actions for the same reason.
  - ADDED `Market`, `Timeframe`, `ReportType`, `ReportFormat`, `SentimentLabel`,
    `RiskLevel` and `DocumentType` — vocabulary required by the market overview,
    reporting and news subsystems introduced in this pass.
"""
from enum import Enum


class Market(str, Enum):
    """
    A tradable market/region. Drives currency, digit grouping, index universe
    and trading calendar throughout the stack — the single switch behind the
    UI's market selector.
    """
    INDIA = "IN"
    UNITED_STATES = "US"


class Timeframe(str, Enum):
    """Chart/aggregation windows offered by the price + performance APIs."""
    D1 = "1D"
    W1 = "1W"
    M1 = "1M"
    M3 = "3M"
    M6 = "6M"
    Y1 = "1Y"
    Y5 = "5Y"
    MAX = "MAX"

    @property
    def trading_days(self) -> int:
        """Approximate number of trading sessions in this window."""
        return {
            "1D": 2, "1W": 5, "1M": 22, "3M": 66,
            "6M": 126, "1Y": 252, "5Y": 1260, "MAX": 100_000,
        }[self.value]


class SignalAction(str, Enum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @classmethod
    def from_score(cls, score: float) -> "RiskLevel":
        """Maps a 0..1 risk score onto the three-band label the UI renders."""
        if score < 0.34:
            return cls.LOW
        if score < 0.67:
            return cls.MEDIUM
        return cls.HIGH


class ModelTask(str, Enum):
    TREND_CLASSIFICATION = "trend_classification"
    NEXT_DAY_RETURN = "next_day_return"
    VOLATILITY_PREDICTION = "volatility_prediction"
    REGIME_DETECTION = "regime_detection"


class ModelAlgorithm(str, Enum):
    XGBOOST = "xgboost"
    LIGHTGBM = "lightgbm"
    RANDOM_FOREST = "random_forest"


class ModelStage(str, Enum):
    """Mirrors MLflow's stage concept for the lightweight DB-backed registry."""
    STAGING = "staging"
    PRODUCTION = "production"
    ARCHIVED = "archived"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    FILLED = "filled"
    PENDING = "pending"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class DocumentType(str, Enum):
    ANNUAL_REPORT = "annual_report"
    QUARTERLY_REPORT = "quarterly_report"
    EARNINGS_CALL = "earnings_call"
    RESEARCH_REPORT = "research_report"


class SentimentLabel(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"

    @classmethod
    def from_score(cls, score: float | None) -> "SentimentLabel":
        if score is None:
            return cls.NEUTRAL
        if score > 0.15:
            return cls.POSITIVE
        if score < -0.15:
            return cls.NEGATIVE
        return cls.NEUTRAL


class ReportType(str, Enum):
    PORTFOLIO = "portfolio"
    RISK = "risk"
    PREDICTION = "prediction"
    TAX = "tax"


class ReportFormat(str, Enum):
    PDF = "pdf"
    CSV = "csv"
    EXCEL = "excel"

    @property
    def media_type(self) -> str:
        return {
            "pdf": "application/pdf",
            "csv": "text/csv",
            "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }[self.value]

    @property
    def extension(self) -> str:
        return {"pdf": "pdf", "csv": "csv", "excel": "xlsx"}[self.value]


class AuditAction(str, Enum):
    """
    What happened. Auth actions are gone (there is no auth); what remains is the
    set of state-changing / compute-consuming operations worth an immutable
    record, plus the API-call telemetry the admin dashboard aggregates.
    """
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    API_CALL = "api_call"
    PREDICTION_REQUEST = "prediction_request"
    SIGNAL_REQUEST = "signal_request"
    MODEL_TRAINED = "model_trained"
    DOCUMENT_UPLOADED = "document_uploaded"
    COPILOT_QUERY = "copilot_query"
    REPORT_GENERATED = "report_generated"
    ORDER_SUBMITTED = "order_submitted"
