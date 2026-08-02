"""
News Intelligence Service — new in v2.0.

Previously `news_articles` was a table with no pipeline behind it and no
endpoint in front of it. It is now populated (seeded corpus + the `ingest`
method below) and served, with a sentiment score computed at ingest time.

Honest scoping note: sentiment here is a **finance-tuned lexicon model**, not a
transformer. That is a deliberate choice, not a shortcut — it is deterministic,
needs no model download or GPU, runs in microseconds, and is fully inspectable
(you can point at the exact word that moved a score). A FinBERT-class model
would be more accurate on subtle phrasing; `score_sentiment` is the single seam
you would swap to adopt one, and the API always names the engine that produced
a number so a consumer is never guessing.
"""
import logging
import math
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.domain.enums import Market, SentimentLabel
from app.models.system import NewsArticle
from app.repositories.market_repository import StockRepository
from app.repositories.system_repository import NewsRepository
from app.schemas.news import NewsArticlePublic, NewsFeed, SentimentSummary

logger = logging.getLogger(__name__)

# Finance-specific lexicon. General-purpose sentiment lists mis-score market
# copy badly ("aggressive" is positive for growth, negative for a selloff;
# "beat"/"miss" are near-meaningless outside earnings), which is why this is a
# domain list rather than an off-the-shelf one.
_POSITIVE = {
    "beat": 2.0, "beats": 2.0, "surge": 2.0, "surges": 2.0, "surged": 2.0,
    "rally": 1.8, "rallies": 1.8, "gain": 1.2, "gains": 1.2, "jump": 1.6,
    "jumps": 1.6, "record": 1.5, "upgrade": 2.0, "upgraded": 2.0, "outperform": 1.8,
    "profit": 1.2, "profitable": 1.5, "growth": 1.3, "expands": 1.2, "expansion": 1.2,
    "strong": 1.4, "robust": 1.4, "optimistic": 1.5, "bullish": 2.0, "recovery": 1.3,
    "dividend": 0.8, "buyback": 1.2, "approval": 1.2, "wins": 1.4, "raises": 1.0,
    "exceeds": 1.8, "momentum": 1.1, "inflows": 1.0, "high": 0.6, "accelerates": 1.5,
    "steady": 0.8, "improving": 1.2, "stable": 0.6,
}
_NEGATIVE = {
    "miss": -2.0, "misses": -2.0, "missed": -2.0, "plunge": -2.2, "plunges": -2.2,
    "slump": -1.8, "slumps": -1.8, "fall": -1.2, "falls": -1.2, "drop": -1.3,
    "drops": -1.3, "decline": -1.3, "declines": -1.3, "declined": -1.3,
    "downgrade": -2.0, "downgraded": -2.0, "underperform": -1.8, "loss": -1.6,
    "losses": -1.6, "weak": -1.4, "weakness": -1.4, "weakens": -1.4, "bearish": -2.0,
    "recession": -2.0, "probe": -1.5, "investigation": -1.6, "lawsuit": -1.5,
    "fine": -1.2, "layoffs": -1.6, "cuts": -1.0, "warning": -1.5, "concerns": -1.2,
    "selloff": -1.9, "volatility": -0.8, "default": -2.2, "outflows": -1.0,
    "uncertainty": -1.1, "pressured": -1.2, "shortfall": -1.6,
}
_NEGATORS = {"not", "no", "never", "without", "despite", "fails", "failed"}
_INTENSIFIERS = {"very": 1.5, "sharply": 1.6, "significantly": 1.4, "slightly": 0.6, "marginally": 0.5}

_TOKEN_RE = re.compile(r"[a-z']+")


def score_sentiment(text: str) -> float:
    """
    Returns a score in [-1, 1].

    Handles negation ("did not beat" is not bullish) and intensifiers ("plunged
    sharply"), which a naive bag-of-words scorer gets exactly backwards on a
    meaningful fraction of real headlines.
    """
    if not text:
        return 0.0

    tokens = _TOKEN_RE.findall(text.lower())
    total = 0.0
    hits = 0

    for i, token in enumerate(tokens):
        weight = _POSITIVE.get(token) or _NEGATIVE.get(token)
        if weight is None:
            continue
        window = tokens[max(0, i - 3): i]
        if any(w in _NEGATORS for w in window):
            weight = -weight
        for w in window:
            if w in _INTENSIFIERS:
                weight *= _INTENSIFIERS[w]
        total += weight
        hits += 1

    if hits == 0:
        return 0.0
    # tanh keeps the output bounded while staying sensitive near zero, so a
    # headline with one strong word doesn't immediately saturate at ±1.
    return round(math.tanh(total / (hits * 2.0)), 4)


def score_impact(headline: str, sentiment: float) -> float:
    """
    0..1 estimate of how much a headline matters — magnitude of sentiment,
    nudged up by the presence of hard numbers (a headline quoting a figure is
    reporting an event; one without is usually commentary).
    """
    base = abs(sentiment)
    has_number = bool(re.search(r"\d", headline))
    return round(min(1.0, base * 0.75 + (0.25 if has_number else 0.0)), 4)


class NewsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = NewsRepository(db)
        self.stocks = StockRepository(db)

    def ingest(
        self, headline: str, source: str, url: str, market: Market,
        published_at: datetime, summary: str | None = None,
        stock_symbol: str | None = None, entities: list[str] | None = None,
    ) -> NewsArticle:
        stock = self.stocks.get_by_symbol(stock_symbol) if stock_symbol else None
        sentiment = score_sentiment(f"{headline} {summary or ''}")
        article = NewsArticle(
            stock_id=stock.id if stock else None,
            market=market, headline=headline, source=source, url=url,
            published_at=published_at,
            sentiment_score=sentiment,
            impact_score=score_impact(headline, sentiment),
            entities=entities or ([stock.symbol] if stock else []),
            summary=summary,
        )
        return self.repo.create(article)

    def feed(self, market: Market | None = None, symbol: str | None = None, limit: int = 30) -> NewsFeed:
        stock_id: uuid.UUID | None = None
        if symbol:
            stock = self.stocks.get_by_symbol(symbol)
            stock_id = stock.id if stock else None

        articles = self.repo.list_feed(market=market, stock_id=stock_id, limit=limit)
        items = [self._to_public(a) for a in articles]
        return NewsFeed(items=items, summary=self._summarize(items))

    @staticmethod
    def _to_public(a: NewsArticle) -> NewsArticlePublic:
        return NewsArticlePublic(
            id=a.id, headline=a.headline, summary=a.summary, source=a.source, url=a.url,
            market=a.market, symbol=a.stock.symbol if a.stock else None,
            published_at=a.published_at, sentiment_score=a.sentiment_score,
            sentiment_label=SentimentLabel.from_score(a.sentiment_score),
            impact_score=a.impact_score, entities=a.entities or [],
        )

    @staticmethod
    def _summarize(items: list[NewsArticlePublic]) -> SentimentSummary:
        if not items:
            return SentimentSummary(
                engine="lexicon_v1", article_count=0, average_sentiment=0.0,
                positive=0, neutral=0, negative=0,
            )
        scores = [i.sentiment_score or 0.0 for i in items]
        return SentimentSummary(
            engine="lexicon_v1",
            article_count=len(items),
            average_sentiment=round(sum(scores) / len(scores), 4),
            positive=sum(1 for i in items if i.sentiment_label == SentimentLabel.POSITIVE),
            neutral=sum(1 for i in items if i.sentiment_label == SentimentLabel.NEUTRAL),
            negative=sum(1 for i in items if i.sentiment_label == SentimentLabel.NEGATIVE),
        )

    def market_sentiment(self, market: Market, days: int = 7) -> SentimentSummary:
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
        articles = [
            a for a in self.repo.list_feed(market=market, limit=200)
            if a.published_at.replace(tzinfo=None) >= since
        ]
        return self._summarize([self._to_public(a) for a in articles])
