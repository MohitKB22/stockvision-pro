"""
Repositories for the cross-cutting tables: audit logs, news, watchlists,
generated reports and application settings.

All of these are new or newly-populated in v2.0 — the admin dashboard, news
feed, watchlist and settings pages had no persistence layer before.
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Float, func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.enums import AuditAction, Market, ReportType
from app.models.system import (
    AppSetting,
    AuditLog,
    GeneratedReport,
    NewsArticle,
    Watchlist,
    WatchlistItem,
)
from app.repositories.base import BaseRepository


class AuditRepository(BaseRepository[AuditLog]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, AuditLog)

    def list_recent(
        self, limit: int = 100, action: AuditAction | None = None, since: datetime | None = None
    ) -> list[AuditLog]:
        stmt = select(AuditLog)
        if action is not None:
            stmt = stmt.where(AuditLog.action == action)
        if since is not None:
            stmt = stmt.where(AuditLog.timestamp >= since)
        return list(
            self.db.execute(stmt.order_by(AuditLog.timestamp.desc()).limit(limit)).scalars().all()
        )

    def count_since(self, since: datetime, action: AuditAction | None = None) -> int:
        stmt = select(func.count()).select_from(AuditLog).where(AuditLog.timestamp >= since)
        if action is not None:
            stmt = stmt.where(AuditLog.action == action)
        return int(self.db.execute(stmt).scalar_one())

    def counts_by_action(self, since: datetime) -> dict[str, int]:
        rows = self.db.execute(
            select(AuditLog.action, func.count())
            .where(AuditLog.timestamp >= since)
            .group_by(AuditLog.action)
        ).all()
        return {str(action): int(count) for action, count in rows}

    def hourly_api_calls(self, hours: int = 24) -> list[tuple[datetime, int]]:
        """
        API-call volume bucketed by hour, computed in Python from a single
        bounded query rather than with a dialect-specific `date_trunc` — which
        does not exist on SQLite, so a SQL-side version would work in production
        and crash in dev and in the test suite.
        """
        since = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=hours - 1)
        rows = self.db.execute(
            select(AuditLog.timestamp).where(AuditLog.timestamp >= since.replace(tzinfo=None))
        ).scalars().all()

        buckets = {(since + timedelta(hours=i)).replace(tzinfo=None): 0 for i in range(hours)}
        for ts in rows:
            key = ts.replace(minute=0, second=0, microsecond=0, tzinfo=None)
            if key in buckets:
                buckets[key] += 1
        return sorted(buckets.items())

    def average_latency_ms(self, since: datetime) -> float:
        value = self.db.execute(
            select(func.avg(AuditLog.duration_ms.cast(Float)))
            .where(AuditLog.timestamp >= since, AuditLog.duration_ms.is_not(None))
        ).scalar()
        return float(value or 0.0)

    def error_count(self, since: datetime) -> int:
        return int(
            self.db.execute(
                select(func.count()).select_from(AuditLog)
                .where(AuditLog.timestamp >= since, AuditLog.status_code >= 400)
            ).scalar_one()
        )


class NewsRepository(BaseRepository[NewsArticle]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, NewsArticle)

    def list_feed(
        self, market: Market | None = None, stock_id: uuid.UUID | None = None, limit: int = 30
    ) -> list[NewsArticle]:
        stmt = select(NewsArticle).options(selectinload(NewsArticle.stock))
        if market is not None:
            stmt = stmt.where(NewsArticle.market == market)
        if stock_id is not None:
            stmt = stmt.where(NewsArticle.stock_id == stock_id)
        return list(
            self.db.execute(
                stmt.order_by(NewsArticle.published_at.desc()).limit(limit)
            ).scalars().all()
        )

    def average_sentiment(self, market: Market | None = None, since: datetime | None = None) -> float | None:
        stmt = select(func.avg(NewsArticle.sentiment_score)).where(NewsArticle.sentiment_score.is_not(None))
        if market is not None:
            stmt = stmt.where(NewsArticle.market == market)
        if since is not None:
            stmt = stmt.where(NewsArticle.published_at >= since)
        value = self.db.execute(stmt).scalar()
        return float(value) if value is not None else None


class WatchlistRepository(BaseRepository[Watchlist]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, Watchlist)

    def list_all(self, market: Market | None = None) -> list[Watchlist]:
        stmt = select(Watchlist).options(
            selectinload(Watchlist.items).selectinload(WatchlistItem.stock)
        )
        if market is not None:
            stmt = stmt.where(Watchlist.market == market)
        return list(self.db.execute(stmt.order_by(Watchlist.created_at)).scalars().all())

    def get_default(self, market: Market) -> Watchlist | None:
        stmt = (
            select(Watchlist)
            .options(selectinload(Watchlist.items).selectinload(WatchlistItem.stock))
            .where(Watchlist.market == market)
        )
        explicit = self.db.execute(
            stmt.where(Watchlist.is_default.is_(True)).limit(1)
        ).scalar_one_or_none()
        return explicit or self.db.execute(
            stmt.order_by(Watchlist.created_at).limit(1)
        ).scalar_one_or_none()

    def get_with_items(self, watchlist_id: uuid.UUID) -> Watchlist | None:
        return self.db.execute(
            select(Watchlist)
            .options(selectinload(Watchlist.items).selectinload(WatchlistItem.stock))
            .where(Watchlist.id == watchlist_id)
        ).scalar_one_or_none()


class WatchlistItemRepository(BaseRepository[WatchlistItem]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, WatchlistItem)

    def find(self, watchlist_id: uuid.UUID, stock_id: uuid.UUID) -> WatchlistItem | None:
        return self.db.execute(
            select(WatchlistItem).where(
                WatchlistItem.watchlist_id == watchlist_id,
                WatchlistItem.stock_id == stock_id,
            )
        ).scalar_one_or_none()

    def next_position(self, watchlist_id: uuid.UUID) -> int:
        value = self.db.execute(
            select(func.max(WatchlistItem.position)).where(WatchlistItem.watchlist_id == watchlist_id)
        ).scalar()
        return int(value or -1) + 1


class ReportRepository(BaseRepository[GeneratedReport]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, GeneratedReport)

    def list_recent(self, limit: int = 50, report_type: ReportType | None = None) -> list[GeneratedReport]:
        stmt = select(GeneratedReport)
        if report_type is not None:
            stmt = stmt.where(GeneratedReport.report_type == report_type)
        return list(
            self.db.execute(
                stmt.order_by(GeneratedReport.created_at.desc()).limit(limit)
            ).scalars().all()
        )


class SettingsRepository(BaseRepository[AppSetting]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, AppSetting)

    def get_all(self) -> dict[str, dict]:
        return {row.key: row.value for row in self.db.execute(select(AppSetting)).scalars().all()}

    def upsert(self, key: str, value: dict) -> AppSetting:
        existing = self.db.execute(
            select(AppSetting).where(AppSetting.key == key)
        ).scalar_one_or_none()
        if existing:
            existing.value = value
            self.db.commit()
            self.db.refresh(existing)
            return existing
        row = AppSetting(key=key, value=value)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row
