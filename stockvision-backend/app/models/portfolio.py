"""
Portfolio, holdings and order models.

Design decision unchanged from v1: `Order` is the append-only ledger;
`PortfolioHolding` is the current-state projection produced by replaying that
ledger (app/services/portfolio_service.py::replay_orders). Both the live order
path and the backtesting engine write through the same replay, so position maths
can never diverge between them.

CHANGE LOG (v2.0):
  - REMOVED `Portfolio.owner_id` and its FK to `users`. The platform has no
    accounts; a portfolio is simply a portfolio. This is the single change that
    made deleting the entire `users` table possible.
  - ADDED `market`, `cash_balance` and `is_default`, so a portfolio is
    self-describing per market and the dashboard has a deterministic
    "the portfolio" to open without a user preference to consult.
  - ADDED an index on `Order.(portfolio_id, executed_at)` — order replay reads
    the full history in execution order on every single write, and that was a
    sequential scan before.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.enums import Market, OrderSide, OrderStatus
from app.models.base import GUID, IDMixin, TimestampMixin


class Portfolio(Base, IDMixin, TimestampMixin):
    __tablename__ = "portfolios"
    __table_args__ = (Index("ix_portfolios_market", "market"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    market: Mapped[Market] = mapped_column(String(4), nullable=False, default=Market.INDIA)
    base_currency: Mapped[str] = mapped_column(String(10), default="INR")
    benchmark_symbol: Mapped[str] = mapped_column(String(20), default="NIFTY50")
    cash_balance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    holdings: Mapped[list["PortfolioHolding"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Portfolio {self.name} [{self.market}]>"


class PortfolioHolding(Base, IDMixin, TimestampMixin):
    __tablename__ = "portfolio_holdings"
    __table_args__ = (
        Index("ix_holdings_portfolio_stock", "portfolio_id", "stock_id", unique=True),
    )

    portfolio_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    stock_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
    )
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    average_cost: Mapped[float] = mapped_column(Float, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    portfolio: Mapped["Portfolio"] = relationship(back_populates="holdings")
    stock: Mapped["Stock"] = relationship()  # noqa: F821

    def __repr__(self) -> str:
        return f"<PortfolioHolding {self.stock_id} x{self.quantity}>"


class Order(Base, IDMixin, TimestampMixin):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_portfolio_executed", "portfolio_id", "executed_at"),
        Index("ix_orders_stock", "stock_id"),
    )

    portfolio_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    stock_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
    )

    side: Mapped[OrderSide] = mapped_column(String(10), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    transaction_cost: Mapped[float] = mapped_column(Float, default=0.0)
    slippage: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[OrderStatus] = mapped_column(String(20), default=OrderStatus.FILLED)
    # Every order this platform records is paper/simulated — there is no live
    # broker connection. Kept as a column (not an assumption) so a future live
    # integration shares one queryable ledger with the backtester.
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    portfolio: Mapped["Portfolio"] = relationship()
    stock: Mapped["Stock"] = relationship()  # noqa: F821

    def __repr__(self) -> str:
        return f"<Order {self.side} {self.quantity} @ {self.price}>"
