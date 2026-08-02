"""
Portfolio endpoints.

CHANGE LOG (v2.0): auth/RBAC dependencies removed; portfolios are no longer
owner-scoped. New endpoints added for the Portfolio page's transactions,
performance chart and allocation views, which previously had no data source.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import MarketDep
from app.core.exceptions import NotFoundException
from app.domain.enums import AuditAction, Market
from app.domain.markets import get_market
from app.models.portfolio import Order, Portfolio
from app.repositories.market_repository import StockRepository
from app.repositories.portfolio_repository import PortfolioRepository
from app.schemas.common import OperationResult
from app.schemas.portfolio import (
    OrderCreate,
    PerformancePoint,
    PortfolioCreate,
    PortfolioPublic,
    PortfolioSummary,
    PortfolioUpdate,
    TransactionPublic,
)
from app.services.audit_service import AuditService
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/portfolios", tags=["Portfolio Analytics"])


@router.get("", response_model=list[PortfolioPublic], summary="List portfolios")
def list_portfolios(market: Market | None = Query(default=None), db: Session = Depends(get_db)):
    return PortfolioRepository(db).list_all(market=market)


@router.post("", response_model=PortfolioPublic, status_code=201, summary="Create a portfolio")
def create_portfolio(payload: PortfolioCreate, db: Session = Depends(get_db)):
    repo = PortfolioRepository(db)
    data = payload.model_dump()

    # Keep currency and benchmark consistent with the market unless the caller
    # deliberately overrode them: a portfolio in INR benchmarked to the S&P
    # produces a meaningless beta, and nothing downstream would flag it.
    definition = get_market(data["market"])
    if data["base_currency"] == "INR" and definition.currency != "INR":
        data["base_currency"] = definition.currency
    if data["benchmark_symbol"] == "NIFTY50" and definition.benchmark_symbol != "NIFTY50":
        data["benchmark_symbol"] = definition.benchmark_symbol

    portfolio = repo.create(Portfolio(**data))
    # First portfolio for this market becomes the default, so the dashboard has
    # something to open without the user having to set a flag.
    if len(repo.list_all(market=portfolio.market)) == 1:
        portfolio = repo.set_default(portfolio)
    return portfolio


@router.get("/default", response_model=PortfolioPublic, summary="The dashboard's portfolio")
def get_default_portfolio(market: MarketDep, db: Session = Depends(get_db)):
    """
    Resolves which portfolio the dashboard should open with, so the frontend
    never has to guess or hardcode an id. Returns a typed `no_portfolio` code so
    the UI can render an onboarding prompt rather than an error.
    """
    portfolio = PortfolioRepository(db).get_default(market)
    if not portfolio:
        raise NotFoundException(
            "No portfolio exists for this market yet. Create one from the Portfolio page.",
            code="no_portfolio",
        )
    return portfolio


@router.get("/{portfolio_id}", response_model=PortfolioPublic, summary="Portfolio detail")
def get_portfolio(portfolio_id: uuid.UUID, db: Session = Depends(get_db)):
    portfolio = PortfolioRepository(db).get(portfolio_id)
    if not portfolio:
        raise NotFoundException("Portfolio not found")
    return portfolio


@router.patch("/{portfolio_id}", response_model=PortfolioPublic, summary="Update a portfolio")
def update_portfolio(portfolio_id: uuid.UUID, payload: PortfolioUpdate, db: Session = Depends(get_db)):
    repo = PortfolioRepository(db)
    portfolio = repo.get(portfolio_id)
    if not portfolio:
        raise NotFoundException("Portfolio not found")

    changes = payload.model_dump(exclude_none=True)
    make_default = changes.pop("is_default", None)
    if changes:
        portfolio = repo.update(portfolio, **changes)
    if make_default:
        portfolio = repo.set_default(portfolio)
    return portfolio


@router.delete("/{portfolio_id}", response_model=OperationResult, summary="Delete a portfolio")
def delete_portfolio(portfolio_id: uuid.UUID, db: Session = Depends(get_db)):
    repo = PortfolioRepository(db)
    portfolio = repo.get(portfolio_id)
    if not portfolio:
        raise NotFoundException("Portfolio not found")
    repo.delete(portfolio)
    return OperationResult(message="Portfolio deleted.", id=str(portfolio_id))


@router.get("/{portfolio_id}/summary", response_model=PortfolioSummary,
            summary="Holdings, P&L and allocation")
def get_portfolio_summary(portfolio_id: uuid.UUID, db: Session = Depends(get_db)):
    return PortfolioService(db).get_summary(portfolio_id)


@router.get("/{portfolio_id}/performance", response_model=list[PerformancePoint],
            summary="Value over time")
def get_portfolio_performance(
    portfolio_id: uuid.UUID,
    days: int = Query(default=180, ge=7, le=2000),
    db: Session = Depends(get_db),
):
    """
    Constant-holdings valuation series — current positions priced against
    historical closes. See PortfolioService.get_performance for why this is named
    for exactly what it is rather than presented as a time-weighted return.
    """
    return PortfolioService(db).get_performance(portfolio_id, days=days)


@router.get("/{portfolio_id}/transactions", response_model=list[TransactionPublic],
            summary="Order ledger")
def get_transactions(
    portfolio_id: uuid.UUID,
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    return PortfolioService(db).get_transactions(portfolio_id, limit=limit)


@router.post("/{portfolio_id}/orders", response_model=OperationResult, status_code=201,
             summary="Record a buy/sell")
def submit_order(portfolio_id: uuid.UUID, payload: OrderCreate, db: Session = Depends(get_db)):
    """
    Records a simulated order and rebuilds holdings by replaying the full ledger.
    Selling more than is held is rejected (see PortfolioService.record_order).
    """
    stock = StockRepository(db).get_by_symbol(payload.symbol)
    if not stock:
        raise NotFoundException(f"{payload.symbol.upper()} is not listed.")

    order = Order(
        stock_id=stock.id, side=payload.side, quantity=payload.quantity, price=payload.price,
        transaction_cost=payload.transaction_cost, slippage=payload.slippage, notes=payload.notes,
        is_simulated=True,
        executed_at=payload.executed_at or datetime.now(timezone.utc).replace(tzinfo=None),
    )
    created = PortfolioService(db).record_order(portfolio_id, order)
    AuditService(db).log(
        action=AuditAction.ORDER_SUBMITTED,
        resource=f"order:{created.id}",
        detail={"symbol": stock.symbol, "side": payload.side.value, "quantity": payload.quantity},
    )
    return OperationResult(message=f"{payload.side.value.upper()} order filled.", id=str(created.id))
