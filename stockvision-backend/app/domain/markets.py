"""
Market registry — the single source of truth for everything that differs
between the two supported markets (India / United States).

Design decision: this is a plain in-process registry, not a database table.
Market definitions are *code-level* configuration: adding a market means adding
index constituents, a currency formatter and a trading calendar, all of which
need code anyway. Putting it in the DB would create a table that can never be
edited safely at runtime, and would force a query on every request for data
that cannot change within a deploy.

Consumed by app/services/market_overview_service.py, scripts/seed_data.py, and
— via GET /api/v1/markets — the frontend's market switcher, so the UI's
currency symbols and index lists can never drift from the backend's.
"""
from dataclasses import dataclass, field

from app.domain.enums import Market


@dataclass(frozen=True)
class IndexDefinition:
    """A market index and the constituent symbols used to synthesize its level."""
    symbol: str
    name: str
    constituents: tuple[str, ...]


@dataclass(frozen=True)
class MarketDefinition:
    code: Market
    name: str
    currency: str
    currency_symbol: str
    # "indian" -> 12,45,000 (lakh/crore grouping); "western" -> 1,245,000
    digit_grouping: str
    exchange: str
    benchmark_symbol: str
    timezone: str
    session_open: str
    session_close: str
    indices: tuple[IndexDefinition, ...] = field(default_factory=tuple)

    @property
    def index_symbols(self) -> tuple[str, ...]:
        return tuple(i.symbol for i in self.indices)


INDIA = MarketDefinition(
    code=Market.INDIA,
    name="India",
    currency="INR",
    currency_symbol="₹",
    digit_grouping="indian",
    exchange="NSE",
    benchmark_symbol="NIFTY50",
    timezone="Asia/Kolkata",
    session_open="09:15",
    session_close="15:30",
    indices=(
        IndexDefinition("NIFTY50", "NIFTY 50", (
            "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN",
            "BHARTIARTL", "ITC", "LT", "KOTAKBANK", "AXISBANK", "HINDUNILVR",
            "MARUTI", "SUNPHARMA", "TITAN", "WIPRO",
        )),
        IndexDefinition("SENSEX", "SENSEX", (
            "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
            "BHARTIARTL", "ITC", "LT", "HINDUNILVR", "MARUTI",
        )),
        IndexDefinition("BANKNIFTY", "BANK NIFTY", (
            "HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK",
        )),
        IndexDefinition("NIFTYIT", "NIFTY IT", ("TCS", "INFY", "WIPRO")),
    ),
)

UNITED_STATES = MarketDefinition(
    code=Market.UNITED_STATES,
    name="United States",
    currency="USD",
    currency_symbol="$",
    digit_grouping="western",
    exchange="NASDAQ",
    benchmark_symbol="SPX",
    timezone="America/New_York",
    session_open="09:30",
    session_close="16:00",
    indices=(
        IndexDefinition("SPX", "S&P 500", (
            "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA",
            "JPM", "JNJ", "XOM", "V", "WMT", "UNH", "PG",
        )),
        IndexDefinition("NDX", "NASDAQ 100", (
            "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA",
        )),
        IndexDefinition("DJI", "DOW JONES", (
            "JPM", "JNJ", "WMT", "UNH", "PG", "MSFT", "AAPL", "V",
        )),
        IndexDefinition("SOX", "SEMICONDUCTORS", ("NVDA", "AAPL", "MSFT")),
    ),
)

MARKETS: dict[Market, MarketDefinition] = {
    Market.INDIA: INDIA,
    Market.UNITED_STATES: UNITED_STATES,
}


def get_market(code: Market | str) -> MarketDefinition:
    """Look up a market definition, accepting either the enum or its raw code."""
    key = code if isinstance(code, Market) else Market(str(code).upper())
    return MARKETS[key]


def all_markets() -> list[MarketDefinition]:
    return list(MARKETS.values())


def index_definition(code: Market | str, index_symbol: str) -> IndexDefinition | None:
    for idx in get_market(code).indices:
        if idx.symbol == index_symbol.upper():
            return idx
    return None
