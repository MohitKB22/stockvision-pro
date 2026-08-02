"""
Import every model module here so that:
1. `Base.metadata.create_all()` (tests, scripts/seed_data.py) sees all tables.
2. Alembic autogenerate discovers every model via `from app.models import *`.

Note the absence of `User` — the users table was removed in v2.0 along with the
entire authentication subsystem.
"""
from app.models.copilot import CopilotConversation, CopilotQuery
from app.models.market import HistoricalPrice, Stock
from app.models.ml import MLModel, Prediction, Signal
from app.models.portfolio import Order, Portfolio, PortfolioHolding
from app.models.system import (
    AppSetting,
    AuditLog,
    Document,
    DocumentEmbedding,
    GeneratedReport,
    NewsArticle,
    Watchlist,
    WatchlistItem,
)

__all__ = [
    "AppSetting",
    "AuditLog",
    "CopilotConversation",
    "CopilotQuery",
    "Document",
    "DocumentEmbedding",
    "GeneratedReport",
    "HistoricalPrice",
    "MLModel",
    "NewsArticle",
    "Order",
    "Portfolio",
    "PortfolioHolding",
    "Prediction",
    "Signal",
    "Stock",
    "Watchlist",
    "WatchlistItem",
]
