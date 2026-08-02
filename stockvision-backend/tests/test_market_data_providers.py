"""
Tests for app/services/market_data_providers.py using httpx.MockTransport --
this sandbox has no network access to these providers (see that module's
docstring), so every HTTP call here is intercepted and answered with a
realistic fixture response, which lets us genuinely test the parsing/retry/
caching logic without touching the network.
"""
import httpx
import pytest

from app.services import market_data_providers as mdp

_REAL_HTTPX_CLIENT = httpx.Client  # captured before any monkeypatching below


@pytest.fixture(autouse=True)
def clear_cache():
    mdp._CACHE.clear()
    yield
    mdp._CACHE.clear()


class TestAlphaVantageProvider:
    def test_parses_realistic_response_shape(self, monkeypatch):
        fixture = {
            "Time Series (Daily)": {
                "2024-01-02": {"1. open": "185.64", "2. high": "186.95", "3. low": "185.01", "4. close": "185.64", "5. volume": "82488700"},
                "2024-01-03": {"1. open": "184.22", "2. high": "185.88", "3. low": "183.43", "4. close": "184.25", "5. volume": "58414500"},
            }
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=fixture)

        monkeypatch.setattr(httpx, "Client", lambda **kw: _REAL_HTTPX_CLIENT(transport=httpx.MockTransport(handler)))

        provider = mdp.AlphaVantageProvider()
        bars = provider.fetch_daily_bars("AAPL", api_key="fake-key")

        assert len(bars) == 2
        assert bars[0]["timestamp"] < bars[1]["timestamp"]  # sorted ascending
        assert bars[0]["close"] == pytest.approx(185.64)
        assert bars[0]["source"] == "alpha_vantage"

    def test_raises_on_provider_error_message(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"Error Message": "Invalid API call"})

        monkeypatch.setattr(httpx, "Client", lambda **kw: _REAL_HTTPX_CLIENT(transport=httpx.MockTransport(handler)))

        with pytest.raises(ValueError, match="Invalid API call"):
            mdp.AlphaVantageProvider().fetch_daily_bars("BADSYMBOL", api_key="fake-key")

    def test_raises_connection_error_on_rate_limit_note(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"Note": "Thank you for using Alpha Vantage... 5 calls per minute"})

        monkeypatch.setattr(httpx, "Client", lambda **kw: _REAL_HTTPX_CLIENT(transport=httpx.MockTransport(handler)))

        with pytest.raises(ConnectionError, match="rate limit"):
            mdp.AlphaVantageProvider().fetch_daily_bars("AAPL", api_key="fake-key")

    def test_result_is_cached_on_second_call(self, monkeypatch):
        call_count = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            return httpx.Response(200, json={"Time Series (Daily)": {
                "2024-01-02": {"1. open": "1", "2. high": "1", "3. low": "1", "4. close": "1", "5. volume": "1"}
            }})

        monkeypatch.setattr(httpx, "Client", lambda **kw: _REAL_HTTPX_CLIENT(transport=httpx.MockTransport(handler)))

        provider = mdp.AlphaVantageProvider()
        provider.fetch_daily_bars("AAPL", api_key="fake-key")
        provider.fetch_daily_bars("AAPL", api_key="fake-key")
        assert call_count["n"] == 1  # second call served from cache, no new HTTP request


class TestYahooFinanceProvider:
    def test_parses_chart_response_and_skips_null_gaps(self, monkeypatch):
        fixture = {
            "chart": {
                "result": [{
                    "timestamp": [1704153600, 1704240000, 1704326400],
                    "indicators": {"quote": [{
                        "open": [185.5, None, 184.0],
                        "high": [186.9, None, 185.5],
                        "low": [185.0, None, 183.0],
                        "close": [185.6, None, 184.2],  # middle day is a gap (e.g. holiday) -> should be skipped
                        "volume": [82000000, None, 58000000],
                    }]},
                }],
                "error": None,
            }
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=fixture)

        monkeypatch.setattr(httpx, "Client", lambda **kw: _REAL_HTTPX_CLIENT(transport=httpx.MockTransport(handler)))

        bars = mdp.YahooFinanceProvider().fetch_daily_bars("AAPL")
        assert len(bars) == 2  # the null-close day was correctly skipped
        assert bars[0]["source"] == "yahoo_finance"

    def test_raises_on_missing_result(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"chart": {"result": None, "error": {"code": "Not Found"}}})

        monkeypatch.setattr(httpx, "Client", lambda **kw: _REAL_HTTPX_CLIENT(transport=httpx.MockTransport(handler)))

        with pytest.raises(ValueError, match="Yahoo Finance error"):
            mdp.YahooFinanceProvider().fetch_daily_bars("NOSUCHTICKER")


class TestRetryLogic:
    def test_retries_on_500_then_succeeds(self, monkeypatch):
        attempts = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["n"] += 1
            if attempts["n"] < 3:
                return httpx.Response(500)
            return httpx.Response(200, json={"ok": True})

        monkeypatch.setattr(mdp.time, "sleep", lambda *_: None)  # don't actually sleep in tests
        client = httpx.Client(transport=httpx.MockTransport(handler))
        response = mdp._request_with_retry(client, "https://example.invalid/x", {}, max_retries=5)
        assert response.status_code == 200
        assert attempts["n"] == 3

    def test_does_not_retry_on_400(self, monkeypatch):
        attempts = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["n"] += 1
            return httpx.Response(400)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        response = mdp._request_with_retry(client, "https://example.invalid/x", {}, max_retries=5)
        assert response.status_code == 400
        assert attempts["n"] == 1  # no retries for a 4xx

    def test_raises_after_exhausting_retries(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503)

        monkeypatch.setattr(mdp.time, "sleep", lambda *_: None)
        client = httpx.Client(transport=httpx.MockTransport(handler))
        with pytest.raises(ConnectionError):
            mdp._request_with_retry(client, "https://example.invalid/x", {}, max_retries=3)


def test_get_provider_returns_correct_instance():
    assert isinstance(mdp.get_provider("alpha_vantage"), mdp.AlphaVantageProvider)
    assert isinstance(mdp.get_provider("yahoo_finance"), mdp.YahooFinanceProvider)


def test_get_provider_raises_on_unknown_name():
    with pytest.raises(ValueError, match="Unknown market data provider"):
        mdp.get_provider("not_a_real_provider")
