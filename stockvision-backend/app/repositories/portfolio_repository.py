"""
Portfolio repositories.

CHANGE LOG (v2.0):
  - `list_for_owner(owner_id)` REMOVED (no owners any more), replaced by
    `list_all` / `get_default` / `set_default`.
  - Holdings and orders are eager-loaded with their `Stock` relationship where
    the caller always needs it (`selectinload`). This kills the N+1 that made
    the portfolio summary issue one query per holding just to read a symbol.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domain.enums import Market
from app.models.portfolio import Order, Portfolio, PortfolioHolding
from app.repositories.base import BaseRepository


class PortfolioRepository(BaseRepository[Portfolio]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, Portfolio)

    def list_all(self, market: Market | None = None) -> list[Portfolio]:
        stmt = select(Portfolio)
        if market is not None:
            stmt = stmt.where(Portfolio.market == market)
        return list(self.db.execute(stmt.order_by(Portfolio.created_at)).scalars().all())

    def get_default(self, market: Market | None = None) -> Portfolio | None:
        """
        The portfolio the dashboard opens with. Prefers an explicitly flagged
        default, then falls back to the oldest portfolio for the market — so the
        dashboard is never blank just because nobody set a flag.
        """
        stmt = select(Portfolio)
        if market is not None:
            stmt = stmt.where(Portfolio.market == market)
        explicit = self.db.execute(
            stmt.where(Portfolio.is_default.is_(True)).limit(1)
        ).scalar_one_or_none()
        if explicit:
            return explicit
        return self.db.execute(stmt.order_by(Portfolio.created_at).limit(1)).scalar_one_or_none()

    def set_default(self, portfolio: Portfolio) -> Portfolio:
        """Clears the flag across the market first — 'default' must be unique."""
        for p in self.list_all(portfolio.market):
            p.is_default = p.id == portfolio.id
        self.db.commit()
        self.db.refresh(portfolio)
        return portfolio


class HoldingRepository(BaseRepository[PortfolioHolding]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, PortfolioHolding)

    def get_for_portfolio(self, portfolio_id: uuid.UUID) -> list[PortfolioHolding]:
        stmt = (
            select(PortfolioHolding)
            .options(selectinload(PortfolioHolding.stock))
            .where(PortfolioHolding.portfolio_id == portfolio_id)
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_by_stock(self, portfolio_id: uuid.UUID, stock_id: uuid.UUID) -> PortfolioHolding | None:
        return self.db.execute(
            select(PortfolioHolding).where(
                PortfolioHolding.portfolio_id == portfolio_id,
                PortfolioHolding.stock_id == stock_id,
            )
        ).scalar_one_or_none()

    def delete_for_portfolio(self, portfolio_id: uuid.UUID) -> None:
        """
        Bulk delete in one statement.

        Performance: the holdings rebuild previously deleted rows one-by-one with
        a commit per row. For a 20-position portfolio that was 20 DELETEs and 20
        transactions on every single order — now one statement, one commit.
        """
        self.db.query(PortfolioHolding).filter(
            PortfolioHolding.portfolio_id == portfolio_id
        ).delete(synchronize_session=False)


class OrderRepository(BaseRepository[Order]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, Order)

    def get_for_portfolio(
        self, portfolio_id: uuid.UUID, *, limit: int | None = None, newest_first: bool = False
    ) -> list[Order]:
        stmt = (
            select(Order)
            .options(selectinload(Order.stock))
            .where(Order.portfolio_id == portfolio_id)
        )
        stmt = stmt.order_by(Order.executed_at.desc() if newest_first else Order.executed_at)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.execute(stmt).scalars().all())
