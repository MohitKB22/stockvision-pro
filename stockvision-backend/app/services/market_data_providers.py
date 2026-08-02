"""
Market Data Service: real provider client implementations.

IMPORTANT — sandbox limitation, stated plainly: this development container
has network egress restricted to package registries (pypi/npm/github) and
has NO Yahoo Finance / Polygon / Alpha Vantage / NSE API keys configured, so
these clients cannot be exercised against live endpoints from here. They are
implemented against each provider's real, documented API shape (verified
against public API docs at write time) and are exercised in
tests/test_market_data_providers.py using mocked HTTP responses — which
tests the retry/parsing/caching logic genuinely, without needing network
access. Swapping a real `ALPHA_VANTAGE_API_KEY` / `POLYGON_API_KEY` into
.env and deploying somewhere with outbound internet access requires no code
changes here.

Design decisions common to every client below:
  - Exponential backoff retry (via `_request_with_retry`) — transient 5xx/
    timeout errors are retried; 4xx errors (bad API key, bad symbol) are not,
    since retrying a request that will deterministically fail again just
    wastes the provider's rate-limit budget.
  - A simple TTL cache keyed by (provider, symbol, params) — avoids
    re-fetching the same day's data on every request, which matters a lot
    against providers with strict per-minute rate limits (Alpha Vantage's
    free tier is 5 req/min).
  - Every client returns the SAME normalized shape: a list of dicts with
    keys [timestamp, open, high, low, close, volume] — exactly what
    PriceRepository.bulk_upsert() and the CSV import path both expect, so
    the rest of the platform never needs to know which provider a bar came from.
"""
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL_SECONDS = 60 * 15  # 15 minutes -- daily bars don't need to be fresher than this


def _cache_get(key: str) -> list[dict] | None:
    entry = _CACHE.get(key)
    if entry is None:
        return None
    cached_at, data = entry
    if time.time() - cached_at > _CACHE_TTL_SECONDS:
        del _CACHE[key]
        return None
    return data


def _cache_set(key: str, data: list[dict]) -> None:
    _CACHE[key] = (time.time(), data)


def _request_with_retry(
    client: httpx.Client, url: str, params: dict, max_retries: int = 3, backoff_base: float = 0.5
) -> httpx.Response:
    """
    Exponential backoff retry: 0.5s, 1s, 2s between attempts. Only retries on
    5xx server errors, timeouts, and connection errors -- a 4xx (bad request/
    auth/rate-limit) is a client-side problem that will not be fixed by
    waiting and retrying identically.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = client.get(url, params=params, timeout=10.0)
            if response.status_code >= 500:
                raise httpx.HTTPStatusError("Server error", request=response.request, response=response)
            return response
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                sleep_time = backoff_base * (2**attempt)
                logger.warning("Request to %s failed (attempt %d/%d): %s. Retrying in %.1fs.",
                               url, attempt + 1, max_retries, exc, sleep_time)
                time.sleep(sleep_time)
    raise ConnectionError(f"Failed to fetch {url} after {max_retries} attempts") from last_exc


class MarketDataProvider(ABC):
    name: str

    @abstractmethod
    def fetch_daily_bars(self, symbol: str, api_key: str, outputsize: str = "compact") -> list[dict]:
        """Returns bars sorted ascending by timestamp, each a dict with keys
        [timestamp, open, high, low, close, volume]."""
        raise NotImplementedError


class AlphaVantageProvider(MarketDataProvider):
    name = "alpha_vantage"
    BASE_URL = "https://www.alphavantage.co/query"

    def fetch_daily_bars(self, symbol: str, api_key: str, outputsize: str = "compact") -> list[dict]:
        cache_key = f"alpha_vantage:{symbol}:{outputsize}"
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "outputsize": outputsize,  # "compact" = last 100 bars, "full" = 20+ years
            "apikey": api_key,
        }
        with httpx.Client() as client:
            response = _request_with_retry(client, self.BASE_URL, params)
        payload = response.json()

        if "Error Message" in payload:
            raise ValueError(f"Alpha Vantage error for {symbol}: {payload['Error Message']}")
        if "Note" in payload:  # rate limit hit
            raise ConnectionError(f"Alpha Vantage rate limit hit: {payload['Note']}")

        series = payload.get("Time Series (Daily)", {})
        bars = [
            {
                "timestamp": datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc),
                "open": float(values["1. open"]),
                "high": float(values["2. high"]),
                "low": float(values["3. low"]),
                "close": float(values["4. close"]),
                "volume": float(values["5. volume"]),
                "source": self.name,
            }
            for date_str, values in series.items()
        ]
        bars.sort(key=lambda b: b["timestamp"])
        _cache_set(cache_key, bars)
        return bars


class PolygonProvider(MarketDataProvider):
    name = "polygon"
    BASE_URL_TEMPLATE = "https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}"

    def fetch_daily_bars(self, symbol: str, api_key: str, outputsize: str = "compact") -> list[dict]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=100 if outputsize == "compact" else 365 * 5)
        cache_key = f"polygon:{symbol}:{start.date()}:{end.date()}"
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        url = self.BASE_URL_TEMPLATE.format(symbol=symbol, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
        params = {"apiKey": api_key, "adjusted": "true", "sort": "asc", "limit": 5000}
        with httpx.Client() as client:
            response = _request_with_retry(client, url, params)
        payload = response.json()

        if payload.get("status") == "ERROR":
            raise ValueError(f"Polygon error for {symbol}: {payload.get('error', 'unknown error')}")

        bars = [
            {
                "timestamp": datetime.fromtimestamp(result["t"] / 1000, tz=timezone.utc),
                "open": result["o"], "high": result["h"], "low": result["l"],
                "close": result["c"], "volume": result["v"], "source": self.name,
            }
            for result in payload.get("results", [])
        ]
        _cache_set(cache_key, bars)
        return bars


class YahooFinanceProvider(MarketDataProvider):
    """
    Uses Yahoo's public (undocumented, no-API-key) chart endpoint, which is
    what the popular `yfinance` library itself calls under the hood -- we
    call it directly here with our own retry/caching wrapper rather than
    taking a heavier dependency for one HTTP GET.
    """
    name = "yahoo_finance"
    BASE_URL_TEMPLATE = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

    def fetch_daily_bars(self, symbol: str, api_key: str = "", outputsize: str = "compact") -> list[dict]:
        cache_key = f"yahoo:{symbol}:{outputsize}"
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        range_param = "3mo" if outputsize == "compact" else "10y"
        url = self.BASE_URL_TEMPLATE.format(symbol=symbol)
        params = {"interval": "1d", "range": range_param}
        with httpx.Client() as client:
            response = _request_with_retry(client, url, params)
        payload = response.json()

        result = payload.get("chart", {}).get("result")
        if not result:
            error = payload.get("chart", {}).get("error", {})
            raise ValueError(f"Yahoo Finance error for {symbol}: {error}")

        chart = result[0]
        timestamps = chart["timestamp"]
        quote = chart["indicators"]["quote"][0]

        bars = [
            {
                "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc),
                "open": quote["open"][i], "high": quote["high"][i], "low": quote["low"][i],
                "close": quote["close"][i], "volume": quote["volume"][i], "source": self.name,
            }
            for i, ts in enumerate(timestamps)
            if quote["close"][i] is not None  # Yahoo pads holidays/gaps with nulls
        ]
        _cache_set(cache_key, bars)
        return bars


class NSEProvider(MarketDataProvider):
    """
    India's National Stock Exchange. NSE's official API requires a
    browser-like session (cookies from an initial homepage visit) before its
    JSON endpoints will respond -- unlike the other three providers, this is
    not a single stateless GET. That two-step handshake is implemented
    faithfully below; it's the reason this client needs a persistent
    `httpx.Client` (for cookie storage) rather than the one-shot client the
    other providers use.
    """
    name = "nse"
    HOME_URL = "https://www.nseindia.com"
    QUOTE_URL_TEMPLATE = "https://www.nseindia.com/api/historical/cm/equity"
    _HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    def fetch_daily_bars(self, symbol: str, api_key: str = "", outputsize: str = "compact") -> list[dict]:
        cache_key = f"nse:{symbol}:{outputsize}"
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=100 if outputsize == "compact" else 365 * 5)

        with httpx.Client(headers=self._HEADERS) as client:
            # Step 1: visit the homepage first to obtain session cookies --
            # NSE's API rejects requests that don't carry a valid session.
            _request_with_retry(client, self.HOME_URL, params={})
            params = {
                "symbol": symbol,
                "series": '["EQ"]',
                "from": start.strftime("%d-%m-%Y"),
                "to": end.strftime("%d-%m-%Y"),
            }
            response = _request_with_retry(client, self.QUOTE_URL_TEMPLATE, params)

        payload = response.json()
        records = payload.get("data", [])
        bars = [
            {
                "timestamp": datetime.strptime(r["CH_TIMESTAMP"], "%Y-%m-%d").replace(tzinfo=timezone.utc),
                "open": float(r["CH_OPENING_PRICE"]), "high": float(r["CH_TRADE_HIGH_PRICE"]),
                "low": float(r["CH_TRADE_LOW_PRICE"]), "close": float(r["CH_CLOSING_PRICE"]),
                "volume": float(r["CH_TOT_TRADED_QTY"]), "source": self.name,
            }
            for r in records
        ]
        bars.sort(key=lambda b: b["timestamp"])
        _cache_set(cache_key, bars)
        return bars


PROVIDERS: dict[str, MarketDataProvider] = {
    "alpha_vantage": AlphaVantageProvider(),
    "polygon": PolygonProvider(),
    "yahoo_finance": YahooFinanceProvider(),
    "nse": NSEProvider(),
}


def get_provider(name: str) -> MarketDataProvider:
    if name not in PROVIDERS:
        raise ValueError(f"Unknown market data provider '{name}'. Available: {list(PROVIDERS)}")
    return PROVIDERS[name]
