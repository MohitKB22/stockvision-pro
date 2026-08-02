import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import Market


# --- Reference data ------------------------------------------------------------
class StockCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    name: str
    exchange: str
    market: Market = Market.INDIA
    sector: str | None = None
    industry: str | None = None
    currency: str = "INR"
    market_cap: float | None = None


class StockPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    symbol: str
    name: str
    exchange: str
    market: Market
    sector: str | None
    industry: str | None
    currency: str
    is_index: bool
    market_cap: float | None


# --- Prices ---------------------------------------------------------------------
class PriceBarCreate(BaseModel):
    timestamp: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)
    source: str = "csv_import"


class PriceBarPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str


class PriceBarBulkImport(BaseModel):
    bars: list[PriceBarCreate] = Field(min_length=1, max_length=20_000)


class BulkImportResult(BaseModel):
    symbol: str
    bars_submitted: int
    bars_inserted: int
    duplicates_skipped: int


class FeatureSnapshot(BaseModel):
    """One row of fully computed technical indicators for a single timestamp."""
    timestamp: datetime
    close: float
    indicators: dict[str, float | None]


# --- Quotes / overview -------------------------------------------------------------
class StockQuote(BaseModel):
    stock_id: uuid.UUID
    symbol: str
    name: str
    exchange: str
    market: Market
    sector: str | None
    currency: str
    last_price: float
    previous_close: float
    change: float
    change_pct: float
    volume: float
    avg_volume_30d: float
    week_52_high: float
    week_52_low: float
    market_cap: float | None = None
    sparkline: list[float] = Field(default_factory=list, description="Last 30 closes, oldest first.")


class IndexQuote(BaseModel):
    symbol: str
    name: str
    market: Market
    level: float
    previous_close: float
    change: float
    change_pct: float
    sparkline: list[float] = Field(default_factory=list)
    constituent_count: int
    is_synthetic: bool = Field(
        description="True when the level is derived from constituents rather than a stored index instrument."
    )


class MoverQuote(BaseModel):
    symbol: str
    name: str
    sector: str | None
    last_price: float
    change: float
    change_pct: float
    volume: float
    turnover: float
    sparkline: list[float] = Field(default_factory=list)


class SectorPerformance(BaseModel):
    sector: str
    change_pct: float
    advancers: int
    decliners: int
    constituent_count: int
    total_turnover: float
    market_cap: float
    top_symbol: str
    bottom_symbol: str


class MarketBreadth(BaseModel):
    market: Market
    total: int
    advancers: int
    decliners: int
    unchanged: int
    advance_decline_ratio: float
    new_highs: int
    new_lows: int
    above_avg_volume: int
    total_turnover: float


class WeekRangeEntry(BaseModel):
    symbol: str
    name: str
    last_price: float
    week_52_high: float
    week_52_low: float
    pct_from_high: float
    pct_from_low: float
    position_in_range: float = Field(description="0 = at the 52-week low, 1 = at the 52-week high.")


class MarketOverview(BaseModel):
    market: Market
    currency: str
    currency_symbol: str
    indices: list[IndexQuote]
    gainers: list[MoverQuote]
    losers: list[MoverQuote]
    most_active: list[MoverQuote]
    sectors: list[SectorPerformance]
    breadth: MarketBreadth


class MoversResponse(BaseModel):
    gainers: list[MoverQuote]
    losers: list[MoverQuote]
    most_active: list[MoverQuote]


class WeekRangeResponse(BaseModel):
    near_52_week_high: list[WeekRangeEntry]
    near_52_week_low: list[WeekRangeEntry]


class HeatmapEntry(BaseModel):
    symbol: str
    name: str
    sector: str
    change_pct: float
    market_cap: float
    last_price: float
    turnover: float


class IndexDefinitionPublic(BaseModel):
    symbol: str
    name: str
    constituent_count: int


class MarketDefinitionPublic(BaseModel):
    """Served by GET /markets so the UI's currency, grouping and index list can
    never drift from the backend's."""
    code: Market
    name: str
    currency: str
    currency_symbol: str
    digit_grouping: str
    exchange: str
    benchmark_symbol: str
    timezone: str
    session_open: str
    session_close: str
    indices: list[IndexDefinitionPublic]


class SessionStatus(BaseModel):
    market: Market
    timezone: str
    local_time: str
    session_open: str
    session_close: str
    is_open: bool
    is_weekday: bool
    holiday_calendar_applied: bool = Field(
        description="False — exchange holiday calendars are not modelled, so a holiday reads as open."
    )
