"""
Market data endpoints: reference data, price history and engineered features.

CHANGE LOG (v2.0): every `Depends(get_current_user)` / `Depends(require_roles(...))`
removed — the platform is unauthenticated by design. Pagination is now a shared
dependency with a hard `limit` ceiling instead of per-endpoint literals.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import MarketDep, PaginationDep
from app.core.exceptions import AlreadyExistsException, NotFoundException
from app.domain.enums import Market
from app.models.market import Stock
from app.repositories.market_repository import PriceRepository, StockRepository
from app.schemas.market import (
    BulkImportResult,
    FeatureSnapshot,
    PriceBarBulkImport,
    PriceBarPublic,
    StockCreate,
    StockPublic,
)
from app.services.feature_engineering_service import FeatureEngineeringService

router = APIRouter(tags=["Market Data"])


@router.get("/stocks", response_model=list[StockPublic], summary="List listed instruments")
def list_stocks(
    pagination: PaginationDep,
    market: Market | None = Query(default=None, description="Filter by market; omit for all."),
    sector: str | None = Query(default=None),
    include_indices: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    repo = StockRepository(db)
    stocks = repo.list_equities(
        market=market, sector=sector, skip=pagination.skip, limit=pagination.limit
    )
    if include_indices:
        stocks = stocks + repo.list_indices(market=market)
    return stocks


@router.get("/stocks/search", response_model=list[StockPublic], summary="Symbol/name search")
def search_stocks(
    q: str = Query(min_length=1, max_length=64),
    market: Market | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Backs the global command-palette search in the top bar."""
    return StockRepository(db).search(q, market=market, limit=limit)


@router.get("/stocks/sectors", response_model=list[str], summary="Distinct sectors")
def list_sectors(market: MarketDep, db: Session = Depends(get_db)):
    return StockRepository(db).list_sectors(market=market)


@router.post("/stocks", response_model=StockPublic, status_code=201, summary="Register an instrument")
def create_stock(payload: StockCreate, db: Session = Depends(get_db)):
    repo = StockRepository(db)
    if repo.get_by_symbol(payload.symbol):
        raise AlreadyExistsException(f"{payload.symbol.upper()} is already registered.")
    data = payload.model_dump(exclude={"symbol"})
    return repo.create(Stock(**data, symbol=payload.symbol.upper()))


@router.get("/stocks/{symbol}", response_model=StockPublic, summary="Instrument detail")
def get_stock(symbol: str, db: Session = Depends(get_db)):
    stock = StockRepository(db).get_by_symbol(symbol)
    if not stock:
        raise NotFoundException(f"{symbol.upper()} is not listed.")
    return stock


@router.post("/stocks/{symbol}/prices", response_model=BulkImportResult, status_code=201,
             summary="Idempotent bulk price import")
def bulk_import_prices(symbol: str, payload: PriceBarBulkImport, db: Session = Depends(get_db)):
    """
    Duplicate (symbol, timestamp) pairs are silently skipped, so re-submitting
    the same CSV is always safe — see PriceRepository.bulk_upsert.
    """
    stock = StockRepository(db).get_by_symbol(symbol)
    if not stock:
        raise NotFoundException(f"{symbol.upper()} is not listed — register it first via POST /stocks.")

    bars = [bar.model_dump() for bar in payload.bars]
    inserted = PriceRepository(db).bulk_upsert(stock.id, bars)
    return BulkImportResult(
        symbol=symbol.upper(), bars_submitted=len(bars),
        bars_inserted=inserted, duplicates_skipped=len(bars) - inserted,
    )


@router.get("/stocks/{symbol}/prices", response_model=list[PriceBarPublic], summary="OHLCV history")
def get_prices(
    symbol: str,
    limit: int = Query(default=250, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    stock = StockRepository(db).get_by_symbol(symbol)
    if not stock:
        raise NotFoundException(f"{symbol.upper()} is not listed.")
    return PriceRepository(db).list_bars(stock.id, limit=limit)


@router.get("/stocks/{symbol}/features", response_model=list[FeatureSnapshot],
            summary="Engineered technical indicators")
def get_features(
    symbol: str,
    limit: int = Query(default=200, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    """The full vectorized indicator set (RSI, MACD, Bollinger, SuperTrend, ADX, ...)."""
    return FeatureEngineeringService(db).compute_features(symbol, limit=limit)
