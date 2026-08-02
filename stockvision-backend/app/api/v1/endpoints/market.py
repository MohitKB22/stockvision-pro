"""
Market Overview endpoints — new in v2.0.

Everything here is computed from stored price history (see
app/services/market_overview_service.py). No endpoint in this module returns a
hardcoded or sampled value.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import MarketDep
from app.domain.markets import all_markets, get_market
from app.schemas.market import (
    HeatmapEntry,
    IndexDefinitionPublic,
    IndexQuote,
    MarketBreadth,
    MarketDefinitionPublic,
    MarketOverview,
    MoversResponse,
    SectorPerformance,
    SessionStatus,
    StockQuote,
    WeekRangeResponse,
)
from app.services.market_overview_service import MarketOverviewService

router = APIRouter(prefix="/market", tags=["Market Overview"])

# A second, unprefixed router so the market registry lives at the natural
# GET /api/v1/markets rather than being contorted into the /market prefix.
markets_router = APIRouter(tags=["Market Overview"])


@markets_router.get("/markets", response_model=list[MarketDefinitionPublic], summary="Supported markets")
def list_markets():
    """
    The source of truth for the UI's market switcher, currency symbols and digit
    grouping, so those can never drift from the backend's own definitions.
    """
    return [
        MarketDefinitionPublic(
            code=d.code, name=d.name, currency=d.currency, currency_symbol=d.currency_symbol,
            digit_grouping=d.digit_grouping, exchange=d.exchange,
            benchmark_symbol=d.benchmark_symbol, timezone=d.timezone,
            session_open=d.session_open, session_close=d.session_close,
            indices=[
                IndexDefinitionPublic(symbol=i.symbol, name=i.name, constituent_count=len(i.constituents))
                for i in d.indices
            ],
        )
        for d in all_markets()
    ]


@router.get("/overview", response_model=MarketOverview, summary="Full market overview")
def market_overview(
    market: MarketDep,
    mover_limit: int = Query(default=6, ge=1, le=25),
    db: Session = Depends(get_db),
):
    return MarketOverviewService(db).overview(market, mover_limit=mover_limit)


@router.get("/indices", response_model=list[IndexQuote], summary="Index levels")
def indices(market: MarketDep, db: Session = Depends(get_db)):
    return MarketOverviewService(db).indices(market)


@router.get("/indices/{index_symbol}/constituents", response_model=list[StockQuote],
            summary="Index constituents")
def index_constituents(index_symbol: str, market: MarketDep, db: Session = Depends(get_db)):
    return MarketOverviewService(db).index_constituents(market, index_symbol)


@router.get("/movers", response_model=MoversResponse, summary="Gainers, losers, most active")
def movers(
    market: MarketDep,
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    return MoversResponse(**MarketOverviewService(db).movers(market, limit=limit))


@router.get("/sectors", response_model=list[SectorPerformance], summary="Cap-weighted sector performance")
def sectors(market: MarketDep, db: Session = Depends(get_db)):
    return MarketOverviewService(db).sector_performance(market)


@router.get("/heatmap", response_model=list[HeatmapEntry], summary="Treemap heatmap data")
def heatmap(market: MarketDep, db: Session = Depends(get_db)):
    return MarketOverviewService(db).heatmap(market)


@router.get("/breadth", response_model=MarketBreadth, summary="Advance/decline breadth")
def breadth(market: MarketDep, db: Session = Depends(get_db)):
    return MarketOverviewService(db).breadth(market)


@router.get("/52-week", response_model=WeekRangeResponse, summary="52-week highs and lows")
def week_52(
    market: MarketDep,
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    return WeekRangeResponse(**MarketOverviewService(db).week_52_extremes(market, limit=limit))


@router.get("/quotes", response_model=list[StockQuote], summary="Batch quotes")
def quotes(
    symbols: str = Query(description="Comma-separated symbols, e.g. RELIANCE,TCS,INFY"),
    db: Session = Depends(get_db),
):
    """Batch endpoint so a watchlist or ticker strip is one request, not N."""
    requested = [s.strip() for s in symbols.split(",") if s.strip()][:100]
    return MarketOverviewService(db).quotes(requested)


@router.get("/quotes/{symbol}", response_model=StockQuote, summary="Single quote")
def quote(symbol: str, db: Session = Depends(get_db)):
    return MarketOverviewService(db).quote(symbol)


@router.get("/session", response_model=SessionStatus, summary="Trading session status")
def session_status(market: MarketDep):
    """
    Whether the market is open right now, derived from the market definition's
    session window and timezone. Weekend detection is included; exchange holiday
    calendars are NOT modelled, and `holiday_calendar_applied: false` says so
    rather than implying a precision the data does not have.
    """
    definition = get_market(market)
    now = datetime.now(ZoneInfo(definition.timezone))
    open_h, open_m = (int(x) for x in definition.session_open.split(":"))
    close_h, close_m = (int(x) for x in definition.session_close.split(":"))
    opens_at = now.replace(hour=open_h, minute=open_m, second=0, microsecond=0)
    closes_at = now.replace(hour=close_h, minute=close_m, second=0, microsecond=0)
    is_weekday = now.weekday() < 5

    return SessionStatus(
        market=market,
        timezone=definition.timezone,
        local_time=now.isoformat(),
        session_open=definition.session_open,
        session_close=definition.session_close,
        is_open=bool(is_weekday and opens_at <= now <= closes_at),
        is_weekday=is_weekday,
        holiday_calendar_applied=False,
    )
