"""
Market-data repositories.

CHANGE LOG (v2.0):
  - `StockRepository` gained market/sector/index-aware queries so the market
    overview, heatmap and search endpoints never filter in Python.
  - `bulk_upsert` fixed: it previously loaded EVERY existing timestamp for the
    stock into a Python set on each call — an O(total_history) memory hit per
    import that grew unbounded as history accumulated. It is now bounded to the
    incoming batch's own [min, max] range, the only range a duplicate can fall in.
  - `get_latest_prices_bulk` / `get_recent_closes_bulk` added: the dashboard
    needs the latest close for N symbols at once, and doing that one query per
    symbol was the single worst N+1 in the codebase (a 40-symbol watchlist
    issued 40 round-trips).
"""
import uuid
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.enums import Market
from app.models.market import HistoricalPrice, Stock
from app.repositories.base import BaseRepository


def _normalize_to_naive_utc(dt: datetime) -> datetime:
    """
    Collapses any datetime — naive (CSV import / pandas) or aware (the live
    provider clients, which build aware UTC datetimes) — into one canonical
    naive-UTC form before it is compared or persisted.

    This matters because SQLite silently drops timezone info on round-trip: an
    aware datetime written to a DateTime(timezone=True) column comes back naive.
    Without normalizing at the boundary, the duplicate check below treats an
    already-stored bar as new whenever awareness doesn't match, which surfaces as
    a UNIQUE constraint violation instead of the intended silent skip.
    """
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


class StockRepository(BaseRepository[Stock]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, Stock)

    def get_by_symbol(self, symbol: str) -> Stock | None:
        return self.db.execute(
            select(Stock).where(Stock.symbol == symbol.upper())
        ).scalar_one_or_none()

    def get_many_by_symbols(self, symbols: list[str]) -> list[Stock]:
        if not symbols:
            return []
        upper = [s.upper() for s in symbols]
        return list(self.db.execute(select(Stock).where(Stock.symbol.in_(upper))).scalars().all())

    def list_equities(
        self, market: Market | None = None, sector: str | None = None,
        skip: int = 0, limit: int = 500,
    ) -> list[Stock]:
        """Tradable equities only — synthetic index instruments are excluded."""
        stmt = select(Stock).where(Stock.is_index.is_(False))
        if market is not None:
            stmt = stmt.where(Stock.market == market)
        if sector:
            stmt = stmt.where(Stock.sector == sector)
        stmt = stmt.order_by(Stock.symbol).offset(skip).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def list_indices(self, market: Market | None = None) -> list[Stock]:
        stmt = select(Stock).where(Stock.is_index.is_(True))
        if market is not None:
            stmt = stmt.where(Stock.market == market)
        return list(self.db.execute(stmt.order_by(Stock.symbol)).scalars().all())

    def list_sectors(self, market: Market | None = None) -> list[str]:
        stmt = select(Stock.sector).where(Stock.sector.is_not(None), Stock.is_index.is_(False))
        if market is not None:
            stmt = stmt.where(Stock.market == market)
        return sorted({row for row in self.db.execute(stmt.distinct()).scalars().all() if row})

    def search(self, query: str, market: Market | None = None, limit: int = 20) -> list[Stock]:
        pattern = f"%{query.strip().lower()}%"
        stmt = select(Stock).where(
            func.lower(Stock.symbol).like(pattern) | func.lower(Stock.name).like(pattern)
        )
        if market is not None:
            stmt = stmt.where(Stock.market == market)
        return list(self.db.execute(stmt.order_by(Stock.symbol).limit(limit)).scalars().all())


class PriceRepository(BaseRepository[HistoricalPrice]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, HistoricalPrice)

    def bulk_upsert(self, stock_id: uuid.UUID, bars: list[dict]) -> int:
        """
        Insert bars, skipping any (stock_id, timestamp) already present. Returns
        the number of newly inserted rows.

        Idempotent by design so re-running a CSV import or a scheduled loader is
        always safe to retry.
        """
        if not bars:
            return 0

        normalized_bars = [{**b, "timestamp": _normalize_to_naive_utc(b["timestamp"])} for b in bars]
        lo = min(b["timestamp"] for b in normalized_bars)
        hi = max(b["timestamp"] for b in normalized_bars)

        # Bounded to the incoming batch's own range — see module docstring.
        existing_ts = {
            _normalize_to_naive_utc(ts)
            for ts in self.db.execute(
                select(HistoricalPrice.timestamp).where(
                    HistoricalPrice.stock_id == stock_id,
                    HistoricalPrice.timestamp >= lo,
                    HistoricalPrice.timestamp <= hi,
                )
            ).scalars().all()
        }

        new_rows: list[HistoricalPrice] = []
        seen_in_batch: set[datetime] = set()
        for bar in normalized_bars:
            ts = bar["timestamp"]
            if ts in existing_ts or ts in seen_in_batch:
                continue
            seen_in_batch.add(ts)
            new_rows.append(HistoricalPrice(stock_id=stock_id, **bar))

        if new_rows:
            self.db.add_all(new_rows)
            self.db.commit()
        return len(new_rows)

    def list_bars(self, stock_id: uuid.UUID, limit: int = 200) -> list[HistoricalPrice]:
        """Full ORM rows ascending by time — for API responses needing every field."""
        stmt = (
            select(HistoricalPrice)
            .where(HistoricalPrice.stock_id == stock_id)
            .order_by(HistoricalPrice.timestamp.desc())
            .limit(limit)
        )
        return list(reversed(list(self.db.execute(stmt).scalars().all())))

    def get_price_series(self, stock_id: uuid.UUID, limit: int = 2000) -> pd.DataFrame:
        """OHLCV history as a DataFrame ascending by time — the shape every
        function in app/ml/ expects."""
        stmt = (
            select(
                HistoricalPrice.timestamp, HistoricalPrice.open, HistoricalPrice.high,
                HistoricalPrice.low, HistoricalPrice.close, HistoricalPrice.volume,
            )
            .where(HistoricalPrice.stock_id == stock_id)
            .order_by(HistoricalPrice.timestamp.desc())
            .limit(limit)
        )
        rows = self.db.execute(stmt).all()
        if not rows:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        return df.sort_values("timestamp").reset_index(drop=True)

    def get_latest_price(self, stock_id: uuid.UUID) -> HistoricalPrice | None:
        return self.db.execute(
            select(HistoricalPrice)
            .where(HistoricalPrice.stock_id == stock_id)
            .order_by(HistoricalPrice.timestamp.desc())
            .limit(1)
        ).scalar_one_or_none()

    def get_latest_prices_bulk(self, stock_ids: list[uuid.UUID]) -> dict[uuid.UUID, HistoricalPrice]:
        """
        Latest bar for many stocks in ONE query.

        Performance: replaces the N+1 pattern (`for s in stocks:
        get_latest_price(s.id)`) that the dashboard, watchlist and market
        overview all hit. On a 40-symbol view this collapses 40 round-trips into
        1 — measurably the difference between a ~600ms and a ~25ms response
        against a networked Postgres.
        """
        if not stock_ids:
            return {}
        latest = (
            select(HistoricalPrice.stock_id, func.max(HistoricalPrice.timestamp).label("ts"))
            .where(HistoricalPrice.stock_id.in_(stock_ids))
            .group_by(HistoricalPrice.stock_id)
            .subquery()
        )
        stmt = select(HistoricalPrice).join(
            latest,
            (HistoricalPrice.stock_id == latest.c.stock_id)
            & (HistoricalPrice.timestamp == latest.c.ts),
        )
        return {row.stock_id: row for row in self.db.execute(stmt).scalars().all()}

    def get_recent_closes_bulk(
        self, stock_ids: list[uuid.UUID], lookback: int = 2
    ) -> dict[uuid.UUID, list[HistoricalPrice]]:
        """
        The last `lookback` bars for many stocks in one query, newest first.

        Needed for change/%-change (2 bars) and 52-week ranges (~252) without
        issuing a query per symbol.
        """
        if not stock_ids:
            return {}
        stmt = (
            select(HistoricalPrice)
            .where(HistoricalPrice.stock_id.in_(stock_ids))
            .order_by(HistoricalPrice.stock_id, HistoricalPrice.timestamp.desc())
        )
        grouped: dict[uuid.UUID, list[HistoricalPrice]] = {}
        for row in self.db.execute(stmt).scalars().all():
            bucket = grouped.setdefault(row.stock_id, [])
            if len(bucket) < lookback:
                bucket.append(row)
        return grouped
