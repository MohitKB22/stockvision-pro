"""
Tests for app/worker.py. Celery tasks are called via `.apply()`, which runs
the task body synchronously in-process (no broker connection needed) --
exactly what lets these tests verify the real task logic without a running
Redis/RabbitMQ instance, which this sandbox doesn't have.
"""
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.market import Stock
from app.worker import refresh_all_tracked_stocks, refresh_stock_prices


def _make_test_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


class TestRefreshStockPrices:
    def test_refresh_unknown_symbol_is_skipped_not_errored(self, monkeypatch):
        session = _make_test_session()
        monkeypatch.setattr("app.worker.SessionLocal", lambda: session)

        result = refresh_stock_prices.apply(args=("NOSUCHTICKER", "alpha_vantage")).get()
        assert result["status"] == "skipped"

    def test_refresh_known_symbol_upserts_bars(self, monkeypatch):
        session = _make_test_session()
        session.add(Stock(symbol="AAPL", name="Apple Inc.", exchange="NASDAQ"))
        session.commit()
        monkeypatch.setattr("app.worker.SessionLocal", lambda: session)

        fake_bars = [
            {"timestamp": "2024-01-02T00:00:00+00:00", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100, "source": "alpha_vantage"}
        ]
        # Patch datetime string to an actual datetime since bulk_upsert expects one
        import datetime
        fake_bars[0]["timestamp"] = datetime.datetime(2024, 1, 2, tzinfo=datetime.timezone.utc)

        with patch("app.worker.get_provider") as mock_get_provider:
            mock_get_provider.return_value.fetch_daily_bars.return_value = fake_bars
            result = refresh_stock_prices.apply(args=("AAPL", "alpha_vantage")).get()

        assert result["status"] == "ok"
        assert result["bars_inserted"] == 1

    def test_refresh_is_idempotent_on_second_call(self, monkeypatch):
        session = _make_test_session()
        session.add(Stock(symbol="AAPL", name="Apple Inc.", exchange="NASDAQ"))
        session.commit()
        monkeypatch.setattr("app.worker.SessionLocal", lambda: session)

        import datetime
        fake_bars = [{
            "timestamp": datetime.datetime(2024, 1, 2, tzinfo=datetime.timezone.utc),
            "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100, "source": "alpha_vantage",
        }]

        with patch("app.worker.get_provider") as mock_get_provider:
            mock_get_provider.return_value.fetch_daily_bars.return_value = fake_bars
            refresh_stock_prices.apply(args=("AAPL", "alpha_vantage")).get()
            second_result = refresh_stock_prices.apply(args=("AAPL", "alpha_vantage")).get()

        assert second_result["bars_inserted"] == 0  # already loaded -- idempotent


class TestRefreshAllTrackedStocks:
    def test_queues_one_task_per_tracked_stock(self, monkeypatch):
        session = _make_test_session()
        session.add(Stock(symbol="AAPL", name="Apple", exchange="NASDAQ"))
        session.add(Stock(symbol="MSFT", name="Microsoft", exchange="NASDAQ"))
        session.commit()
        monkeypatch.setattr("app.worker.SessionLocal", lambda: session)

        with patch("app.worker.refresh_stock_prices.delay") as mock_delay:
            result = refresh_all_tracked_stocks.apply().get()

        assert result["symbols_queued"] == 2
        assert mock_delay.call_count == 2
