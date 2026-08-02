"""
Market reference + time-series models.

`HistoricalPrice` is deliberately narrow (OHLCV + stock_id + timestamp) because
it is by far the highest-write and highest-scan table in the schema. Everything
derived from it — returns, indicators, index levels, 52-week ranges — is
computed on read rather than stored, so there is exactly one source of truth for
price.

CHANGE LOG (v2.0):
  - ADDED `Stock.market` (IN/US) with an index. Without it every market-scoped
    query had to infer region from `exchange`, a free-text column — which meant
    "NSE" vs "NSE " vs "NASDAQ" string-matching scattered across services.
  - ADDED `Stock.is_index` so synthetic index instruments (NIFTY50, SPX) live in
    the same table as equities and reuse the entire price/indicator pipeline
    instead of needing a parallel schema.
  - ADDED denormalized `market_cap` / `shares_outstanding` — needed for
    cap-weighted index levels and the sector heatmap, and genuinely static
    relative to prices.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.enums import Market
from app.models.base import GUID, IDMixin, TimestampMixin


class Stock(Base, IDMixin, TimestampMixin):
    __tablename__ = "stocks"
    __table_args__ = (
        Index("ix_stocks_market_sector", "market", "sector"),
        Index("ix_stocks_market_is_index", "market", "is_index"),
    )

    symbol: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    exchange: Mapped[str] = mapped_column(String(50), nullable=False)
    market: Mapped[Market] = mapped_column(String(4), nullable=False, index=True, default=Market.INDIA)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    is_index: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    shares_outstanding: Mapped[float | None] = mapped_column(Float, nullable=True)

    prices: Mapped[list["HistoricalPrice"]] = relationship(
        back_populates="stock", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Stock {self.symbol} [{self.market}]>"


class HistoricalPrice(Base, IDMixin):
    __tablename__ = "historical_prices"
    __table_args__ = (
        # Uniqueness is what makes the bulk importer idempotent — re-uploading
        # the same CSV can never duplicate a bar.
        Index("ix_historical_prices_stock_ts", "stock_id", "timestamp", unique=True),
        Index("ix_historical_prices_ts", "timestamp"),
    )

    stock_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(50), default="csv_import")

    stock: Mapped["Stock"] = relationship(back_populates="prices")

    def __repr__(self) -> str:
        return f"<HistoricalPrice {self.stock_id} @ {self.timestamp}>"
