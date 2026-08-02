import uuid

from pydantic import BaseModel, Field

from app.domain.enums import Market
from app.schemas.market import StockQuote


class WatchlistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    market: Market = Market.INDIA


class WatchlistItemCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    alert_above: float | None = Field(default=None, gt=0)
    alert_below: float | None = Field(default=None, gt=0)


class WatchlistItemPublic(BaseModel):
    id: uuid.UUID
    symbol: str
    name: str
    sector: str | None
    position: int
    alert_above: float | None
    alert_below: float | None
    quote: StockQuote | None
    alert_triggered: bool


class WatchlistPublic(BaseModel):
    id: uuid.UUID
    name: str
    market: Market
    is_default: bool
    item_count: int
    items: list[WatchlistItemPublic]
