"""
SQLAlchemy engine + session factory.

DATABASE_URL drives dialect selection so the *same* codebase targets SQLite
(zero-dependency local dev, and the in-memory DB the test suite uses) or
PostgreSQL in production.

CHANGE LOG (v2.0):
  - Connection pooling is now explicitly configured for PostgreSQL
    (`pool_size` / `max_overflow` / `pool_recycle`). Previously the engine ran on
    SQLAlchemy's default pool with no recycle, which against a managed Postgres
    with an idle timeout produces intermittent "server closed the connection
    unexpectedly" errors under low traffic — the classic stale-pooled-connection
    bug that only shows up in production.
  - SQLite gets `PRAGMA foreign_keys=ON`. SQLite does NOT enforce foreign keys
    unless asked per-connection, so every `ondelete="CASCADE"` in the models was
    silently a no-op in dev and in tests: deleting a portfolio left orphaned
    holdings and orders behind, and no test could ever have caught it.
"""
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

if settings.is_sqlite:
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=settings.DB_ECHO,
        pool_pre_ping=True,
    )
else:
    engine = create_engine(
        settings.DATABASE_URL,
        echo=settings.DB_ECHO,
        pool_pre_ping=True,       # validates a connection before handing it out
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_recycle=1800,        # recycle before typical managed-PG idle timeouts
    )


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:
    """Enable FK enforcement + WAL on SQLite connections only."""
    if not settings.is_sqlite:
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
    finally:
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model in app/models/."""


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency: yields a request-scoped session and always closes it.

    Bug fix: the session is now rolled back on exception before closing. Without
    it a failed request could return its connection to the pool holding an
    aborted transaction, and the *next* request to borrow that connection would
    fail with `InFailedSqlTransaction` — a genuinely confusing bug, because the
    failure surfaces on an unrelated request.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
