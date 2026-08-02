"""
Portfolio Service.

Design decision (unchanged): `PortfolioHolding` rows are a projection rebuilt by
replaying every Order in execution order — never mutated incrementally in
scattered places. One code path answers "what does this portfolio hold".

CHANGE LOG (v2.0):
  - `replay_orders` now tracks REALIZED P&L on sells. Previously a sell only
    reduced quantity and the realized gain was thrown away, so a portfolio that
    had taken profit reported a total return that understated reality.
  - Holdings rebuild is a single bulk delete + single bulk insert inside ONE
    transaction. It previously issued a DELETE-and-commit per existing holding
    and an INSERT-and-commit per new one — ~40 transactions per order on a
    20-position portfolio — and a crash midway left the portfolio partially
    rebuilt, because there was no enclosing transaction.
  - `get_summary` uses the bulk price fetch instead of one query per holding
    (N+1), and now also returns day change, realized P&L, asset allocation and
    the performance series the dashboard charts.
"""
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import pandas as pd
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestException, NotFoundException
from app.domain.enums import OrderSide
from app.models.portfolio import Order, PortfolioHolding
from app.repositories.market_repository import PriceRepository, StockRepository
from app.repositories.portfolio_repository import (
    HoldingRepository,
    OrderRepository,
    PortfolioRepository,
)
from app.schemas.portfolio import (
    AllocationSlice,
    HoldingPublic,
    PerformancePoint,
    PortfolioSummary,
    TransactionPublic,
)


class Position:
    """Mutable accumulator used by `replay_orders`."""

    __slots__ = ("average_cost", "quantity", "realized_pnl")

    def __init__(self) -> None:
        self.quantity = 0.0
        self.average_cost = 0.0
        self.realized_pnl = 0.0


def replay_orders(orders: list[Order]) -> dict[uuid.UUID, Position]:
    """
    Pure function: given a list of Orders for one portfolio, return
    {stock_id: Position}.

    Weighted-average-cost method. A BUY raises quantity and re-averages cost
    (including transaction cost and slippage, which are genuinely part of what
    the position cost). A SELL reduces quantity, leaves average cost alone, and
    books realized P&L for the disposed portion.

    Sorting by `executed_at` happens here rather than being assumed: order
    history arrives sorted from the repository, but replay must not DEPEND on
    that — an out-of-order list would otherwise silently produce a different
    average cost.
    """
    positions: dict[uuid.UUID, Position] = defaultdict(Position)

    for order in sorted(orders, key=lambda o: o.executed_at):
        pos = positions[order.stock_id]
        frictions = (order.transaction_cost or 0.0) + (order.slippage or 0.0)

        if order.side == OrderSide.BUY:
            gross_cost = pos.quantity * pos.average_cost + order.quantity * order.price + frictions
            pos.quantity += order.quantity
            pos.average_cost = gross_cost / pos.quantity if pos.quantity > 0 else 0.0
        else:
            sold = min(order.quantity, pos.quantity)
            pos.realized_pnl += sold * (order.price - pos.average_cost) - frictions
            pos.quantity = max(pos.quantity - order.quantity, 0.0)
            if pos.quantity <= 1e-9:
                pos.quantity = 0.0

    # Keep zero-quantity positions only when they carry realized P&L worth
    # reporting; drop pure noise.
    return {
        sid: p for sid, p in positions.items()
        if p.quantity > 1e-9 or abs(p.realized_pnl) > 1e-9
    }


class PortfolioService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.portfolios = PortfolioRepository(db)
        self.holdings = HoldingRepository(db)
        self.orders = OrderRepository(db)
        self.stocks = StockRepository(db)
        self.prices = PriceRepository(db)

    # --- Commands ---------------------------------------------------------
    def record_order(self, portfolio_id: uuid.UUID, order: Order) -> Order:
        portfolio = self.portfolios.get(portfolio_id)
        if not portfolio:
            raise NotFoundException("Portfolio not found")

        if order.side == OrderSide.SELL:
            held = self.holdings.get_by_stock(portfolio_id, order.stock_id)
            available = held.quantity if held else 0.0
            if order.quantity > available + 1e-9:
                # Validation added in v2.0: the API previously accepted a sell
                # for more than was held, producing a negative position that
                # every downstream weight calculation then divided by.
                raise BadRequestException(
                    f"Cannot sell {order.quantity:g} units; only {available:g} held.",
                    context={"available_quantity": available},
                )

        order.portfolio_id = portfolio_id
        created = self.orders.create(order)
        self._rebuild_holdings(portfolio_id)
        return created

    def _rebuild_holdings(self, portfolio_id: uuid.UUID) -> None:
        """Delete + rewrite the projection inside ONE transaction."""
        orders = self.orders.get_for_portfolio(portfolio_id)
        positions = replay_orders(orders)

        self.holdings.delete_for_portfolio(portfolio_id)
        rows = [
            PortfolioHolding(
                portfolio_id=portfolio_id,
                stock_id=stock_id,
                quantity=pos.quantity,
                average_cost=pos.average_cost,
                realized_pnl=pos.realized_pnl,
            )
            for stock_id, pos in positions.items()
            if pos.quantity > 1e-9
        ]
        if rows:
            self.db.add_all(rows)
        self.db.commit()

    # --- Queries -----------------------------------------------------------
    def get_summary(self, portfolio_id: uuid.UUID) -> PortfolioSummary:
        portfolio = self.portfolios.get(portfolio_id)
        if not portfolio:
            raise NotFoundException("Portfolio not found")

        holdings = self.holdings.get_for_portfolio(portfolio_id)
        recent = self.prices.get_recent_closes_bulk([h.stock_id for h in holdings], lookback=2)

        rows: list[HoldingPublic] = []
        sector_value: dict[str, float] = defaultdict(float)
        total_value = total_cost = day_change = realized = 0.0

        for h in holdings:
            stock = h.stock
            bars = recent.get(h.stock_id, [])
            current_price = bars[0].close if bars else h.average_cost
            previous_close = bars[1].close if len(bars) > 1 else current_price

            market_value = h.quantity * current_price
            cost_basis = h.quantity * h.average_cost
            pnl = market_value - cost_basis
            day_delta = h.quantity * (current_price - previous_close)

            total_value += market_value
            total_cost += cost_basis
            day_change += day_delta
            realized += h.realized_pnl or 0.0
            sector_value[stock.sector or "Unclassified"] += market_value

            rows.append(
                HoldingPublic(
                    stock_id=stock.id, symbol=stock.symbol, name=stock.name, sector=stock.sector,
                    quantity=h.quantity, average_cost=h.average_cost,
                    current_price=current_price, previous_close=previous_close,
                    market_value=market_value, cost_basis=cost_basis,
                    unrealized_pnl=pnl,
                    unrealized_pnl_pct=(pnl / cost_basis) if cost_basis > 0 else 0.0,
                    realized_pnl=h.realized_pnl or 0.0,
                    day_change=day_delta,
                    day_change_pct=((current_price - previous_close) / previous_close) if previous_close else 0.0,
                    weight_pct=0.0,  # filled below, once total_value is known
                )
            )

        for row in rows:
            row.weight_pct = (row.market_value / total_value) if total_value > 0 else 0.0
        rows.sort(key=lambda r: r.market_value, reverse=True)

        sector_exposure = [
            AllocationSlice(label=sector, value=value, weight_pct=value / total_value if total_value else 0.0)
            for sector, value in sorted(sector_value.items(), key=lambda kv: -kv[1])
        ]

        cash = portfolio.cash_balance or 0.0
        gross = total_value + cash
        asset_allocation = [
            AllocationSlice(label="Equity", value=total_value, weight_pct=total_value / gross if gross else 0.0),
            AllocationSlice(label="Cash", value=cash, weight_pct=cash / gross if gross else 0.0),
        ]

        return PortfolioSummary(
            portfolio_id=portfolio.id, name=portfolio.name, market=portfolio.market,
            base_currency=portfolio.base_currency, benchmark_symbol=portfolio.benchmark_symbol,
            cash_balance=cash,
            total_market_value=total_value, total_value=gross, total_cost_basis=total_cost,
            total_unrealized_pnl=total_value - total_cost,
            total_unrealized_pnl_pct=((total_value - total_cost) / total_cost) if total_cost > 0 else 0.0,
            total_realized_pnl=realized,
            day_change=day_change,
            day_change_pct=(day_change / (total_value - day_change)) if (total_value - day_change) > 0 else 0.0,
            holding_count=len(rows), holdings=rows,
            sector_exposure=sector_exposure, asset_allocation=asset_allocation,
        )

    def get_performance(self, portfolio_id: uuid.UUID, days: int = 180) -> list[PerformancePoint]:
        """
        Reconstructs the portfolio's market value over time by valuing the
        CURRENT holdings against each historical close.

        Honest limitation, stated rather than hidden: this is a
        constant-holdings ("current positions, historical prices") series, not a
        true time-weighted return that accounts for when each position was
        opened. Computing the latter needs a position snapshot per day; the
        schema supports it (the order ledger is complete) and it is the
        documented next step — but presenting one as the other would be a lie in
        a chart, so the API names the field for what it is.
        """
        holdings = self.holdings.get_for_portfolio(portfolio_id)
        if not holdings:
            return []

        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
        frames: list[pd.Series] = []
        for h in holdings:
            df = self.prices.get_price_series(h.stock_id, limit=days + 30)
            if df.empty:
                continue
            frames.append(df.set_index("timestamp")["close"] * h.quantity)

        if not frames:
            return []

        combined = pd.concat(frames, axis=1).sort_index().ffill().dropna(how="all")
        combined = combined[combined.index >= cutoff]
        totals = combined.sum(axis=1)
        if totals.empty:
            return []

        base = float(totals.iloc[0]) or 1.0
        return [
            PerformancePoint(
                timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                value=float(value),
                return_pct=float(value) / base - 1.0,
            )
            for ts, value in totals.items()
        ]

    def get_transactions(self, portfolio_id: uuid.UUID, limit: int = 200) -> list[TransactionPublic]:
        orders = self.orders.get_for_portfolio(portfolio_id, limit=limit, newest_first=True)
        return [
            TransactionPublic(
                id=o.id, symbol=o.stock.symbol, name=o.stock.name, side=o.side,
                quantity=o.quantity, price=o.price, value=o.quantity * o.price,
                transaction_cost=o.transaction_cost or 0.0, slippage=o.slippage or 0.0,
                status=o.status, is_simulated=o.is_simulated, notes=o.notes,
                executed_at=o.executed_at,
            )
            for o in orders
        ]
