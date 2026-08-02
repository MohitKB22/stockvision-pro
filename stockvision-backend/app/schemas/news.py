import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import Market, SentimentLabel


class NewsArticlePublic(BaseModel):
    id: uuid.UUID
    headline: str
    summary: str | None
    source: str
    url: str
    market: Market
    symbol: str | None
    published_at: datetime
    sentiment_score: float | None
    sentiment_label: SentimentLabel
    impact_score: float | None
    entities: list[str] = Field(default_factory=list)


class SentimentSummary(BaseModel):
    engine: str = Field(
        description="Which scoring engine produced these numbers — see app/services/news_service.py."
    )
    article_count: int
    average_sentiment: float
    positive: int
    neutral: int
    negative: int


class NewsFeed(BaseModel):
    items: list[NewsArticlePublic]
    summary: SentimentSummary
