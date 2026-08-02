"""News Intelligence endpoints — new in v2.0."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import MarketDep
from app.domain.enums import Market
from app.schemas.news import NewsFeed, SentimentSummary
from app.services.news_service import NewsService

router = APIRouter(prefix="/news", tags=["News Intelligence"])


@router.get("", response_model=NewsFeed, summary="News feed with sentiment")
def news_feed(
    market: Market | None = Query(default=None),
    symbol: str | None = Query(default=None, description="Scope to one company."),
    limit: int = Query(default=30, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """
    Each article carries a sentiment score from the finance-tuned lexicon engine
    (see app/services/news_service.py). The `summary.engine` field names the
    engine, so a consumer always knows what produced the numbers.
    """
    return NewsService(db).feed(market=market, symbol=symbol, limit=limit)


@router.get("/sentiment", response_model=SentimentSummary, summary="Aggregate market sentiment")
def market_sentiment(
    market: MarketDep,
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
):
    return NewsService(db).market_sentiment(market, days=days)
