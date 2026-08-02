"""
Direct tests for app/repositories/market_repository.py -- particularly
bulk_upsert's idempotency guarantee, which every retry-safe ingestion path
(CSV import API, and the Celery refresh_stock_prices task) depends on.
"""
import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.market import Stock
from app.repositories.market_repository import PriceRepository, _normalize_to_naive_utc


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _stock(session):
    stock = Stock(symbol="AAPL", name="Apple", exchange="NASDAQ")
    session.add(stock)
    session.commit()
    return stock


class TestNormalizeToNaiveUtc:
    def test_naive_datetime_passed_through_unchanged(self):
        dt = datetime.datetime(2024, 1, 2, 10, 30)
        assert _normalize_to_naive_utc(dt) == dt

    def test_aware_utc_datetime_becomes_naive(self):
        dt = datetime.datetime(2024, 1, 2, 10, 30, tzinfo=datetime.timezone.utc)
        result = _normalize_to_naive_utc(dt)
        assert result.tzinfo is None
        assert result == datetime.datetime(2024, 1, 2, 10, 30)

    def test_aware_non_utc_datetime_is_converted_to_utc_first(self):
        """A timestamp in UTC-5 at 10:30 is 15:30 UTC -- normalization must
        convert before dropping tzinfo, not just strip the offset in place."""
        tz_minus_5 = datetime.timezone(datetime.timedelta(hours=-5))
        dt = datetime.datetime(2024, 1, 2, 10, 30, tzinfo=tz_minus_5)
        result = _normalize_to_naive_utc(dt)
        assert result == datetime.datetime(2024, 1, 2, 15, 30)


class TestBulkUpsertIdempotency:
    def test_basic_insert(self):
        session = _session()
        stock = _stock(session)
        repo = PriceRepository(session)
        bar = {"timestamp": datetime.datetime(2024, 1, 2), "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}
        assert repo.bulk_upsert(stock.id, [bar]) == 1

    def test_reimporting_identical_naive_bars_is_a_noop(self):
        session = _session()
        stock = _stock(session)
        repo = PriceRepository(session)
        bar = {"timestamp": datetime.datetime(2024, 1, 2), "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}
        repo.bulk_upsert(stock.id, [bar])
        assert repo.bulk_upsert(stock.id, [bar]) == 0

    def test_aware_and_naive_timestamps_for_the_same_instant_are_recognized_as_duplicates(self):
        """
        Regression test: a bar loaded once via a live provider client
        (timezone-aware UTC timestamp, per market_data_providers.py) and
        again via CSV import (naive timestamp, per pandas' default) for the
        SAME calendar instant must be recognized as the same bar -- not
        double-inserted, and not raise a UNIQUE constraint IntegrityError.
        """
        session = _session()
        stock = _stock(session)
        repo = PriceRepository(session)

        aware_bar = {
            "timestamp": datetime.datetime(2024, 1, 2, tzinfo=datetime.timezone.utc),
            "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100, "source": "alpha_vantage",
        }
        naive_bar = {
            "timestamp": datetime.datetime(2024, 1, 2),
            "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100, "source": "csv_import",
        }

        assert repo.bulk_upsert(stock.id, [aware_bar]) == 1
        assert repo.bulk_upsert(stock.id, [naive_bar]) == 0  # must NOT raise, must NOT double-insert

    def test_duplicate_timestamps_within_a_single_batch_are_only_inserted_once(self):
        """A batch containing the same timestamp twice (e.g. a malformed
        CSV export) must not attempt two inserts for the same unique key."""
        session = _session()
        stock = _stock(session)
        repo = PriceRepository(session)
        bar = {"timestamp": datetime.datetime(2024, 1, 2), "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}
        assert repo.bulk_upsert(stock.id, [bar, dict(bar)]) == 1

    def test_partial_overlap_only_inserts_new_bars(self):
        session = _session()
        stock = _stock(session)
        repo = PriceRepository(session)
        day1 = {"timestamp": datetime.datetime(2024, 1, 1), "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}
        day2 = {"timestamp": datetime.datetime(2024, 1, 2), "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}
        repo.bulk_upsert(stock.id, [day1])
        assert repo.bulk_upsert(stock.id, [day1, day2]) == 1  # only day2 is new
