"""
Shared model mixins.

Every table gets a UUID primary key (safe to expose in URLs, generatable
client-side, no leaking of sequential-ID row counts) and created_at/updated_at
timestamps, via mixins rather than copy-pasted columns.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import CHAR, TypeDecorator


class UTCDateTime(TypeDecorator):
    """
    A `TIMESTAMP WITH TIME ZONE` column that behaves identically on every dialect.

    The codebase's convention is naive datetimes meaning UTC (see
    `market_repository._normalize_to_naive_utc`). SQLite honours that by accident:
    it drops tzinfo on round-trip, so values always come back naive. PostgreSQL
    returns timezone-AWARE datetimes for the same column, so on the production
    database every comparison between a stored value and a naive cutoff raised
    `TypeError: Invalid comparison between dtype=datetime64[ns, UTC] and datetime`
    (the portfolio performance endpoint failed outright), and every naive value
    written was interpreted in the server's session time zone rather than UTC.

    This type is the one place that difference is absorbed:
      * writes: naive values are taken as UTC; aware values are converted to UTC.
        PostgreSQL receives an aware UTC datetime, so the session time zone no
        longer matters.
      * reads: always a naive UTC datetime, on every dialect — exactly what the
        services (and the test suite, which runs on SQLite) already expect.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(timezone.utc)
        return value if dialect.name == "postgresql" else value.replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None or value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)


class GUID(TypeDecorator):
    """
    Platform-independent UUID type.

    Stores as PostgreSQL's native UUID type in production, and as a CHAR(36)
    in SQLite (used for local dev / this sandbox's test run) — this is the
    kind of dialect difference the repository/service layers should never
    have to know about.
    """
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import UUID as PG_UUID
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value)
        if not isinstance(value, uuid.UUID):
            return str(uuid.UUID(value))
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(value)


class IDMixin:
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), onupdate=func.now()
    )
