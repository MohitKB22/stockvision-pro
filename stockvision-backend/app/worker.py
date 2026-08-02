"""
Celery worker app: background/scheduled jobs.

Design decision: tasks here are thin wrappers that open their OWN DB session
(via SessionLocal directly, not FastAPI's `get_db` dependency, which only
exists for request-scoped injection) and delegate to the exact same
repository/provider code the API uses — a Celery task and an API endpoint
should never have two different implementations of "how prices get loaded".
"""
import logging

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings
from app.core.database import SessionLocal
from app.repositories.market_repository import PriceRepository, StockRepository
from app.services.market_data_providers import get_provider

logger = logging.getLogger(__name__)

celery_app = Celery(
    "stockvision",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_BROKER_URL,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Beat schedule: refresh every tracked stock's prices once daily after US
# markets close (21:30 UTC ≈ 4:30pm ET) — the "Historical Data Loader"
# running on autopilot, per the brief's Market Data Service section.
celery_app.conf.beat_schedule = {
    "refresh-all-stock-prices-daily": {
        "task": "app.worker.refresh_all_tracked_stocks",
        "schedule": crontab(hour=21, minute=30),
    },
}


@celery_app.task(name="app.worker.refresh_stock_prices", bind=True, max_retries=3, default_retry_delay=60)
def refresh_stock_prices(self, symbol: str, provider_name: str = "alpha_vantage") -> dict:
    """
    Fetches fresh daily bars for `symbol` from `provider_name` and
    idempotently upserts them (see PriceRepository.bulk_upsert) — safe to run
    on a schedule indefinitely without ever double-inserting a bar.
    """
    db = SessionLocal()
    try:
        stock_repo = StockRepository(db)
        stock = stock_repo.get_by_symbol(symbol)
        if not stock:
            logger.warning("refresh_stock_prices: symbol %s not found in DB, skipping.", symbol)
            return {"symbol": symbol, "status": "skipped", "reason": "unknown symbol"}

        provider = get_provider(provider_name)
        api_key = {
            "alpha_vantage": settings.ALPHA_VANTAGE_API_KEY,
            "polygon": settings.POLYGON_API_KEY,
        }.get(provider_name, "")

        bars = provider.fetch_daily_bars(symbol, api_key=api_key or "", outputsize="compact")
        inserted = PriceRepository(db).bulk_upsert(stock.id, bars)
        logger.info("refresh_stock_prices: %s -> %d new bars from %s", symbol, inserted, provider_name)
        return {"symbol": symbol, "status": "ok", "bars_fetched": len(bars), "bars_inserted": inserted}
    except ConnectionError as exc:
        # Transient (rate limit, network blip) -- Celery's autoretry backs off
        # and tries again rather than dropping the refresh for the day.
        # `from exc` preserves the original ConnectionError as __cause__, so the
        # traceback shows the network failure that triggered the retry rather
        # than just Celery's Retry wrapper.
        raise self.retry(exc=exc) from exc
    finally:
        db.close()


@celery_app.task(name="app.worker.refresh_all_tracked_stocks")
def refresh_all_tracked_stocks(provider_name: str = "alpha_vantage") -> dict:
    """Fans out refresh_stock_prices for every stock currently in the DB."""
    db = SessionLocal()
    try:
        symbols = [s.symbol for s in StockRepository(db).list(limit=10_000)]
    finally:
        db.close()

    for symbol in symbols:
        refresh_stock_prices.delay(symbol, provider_name)
    return {"symbols_queued": len(symbols)}
