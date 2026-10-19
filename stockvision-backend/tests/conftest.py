"""
Shared pytest fixtures.

Each test function gets a FRESH in-memory SQLite database (StaticPool-backed so
every connection sees the same DB) — not the dev stockvision.db file — so tests
are isolated from each other and from local state, and can run in any order.

CHANGE LOG (v2.0): the `auth_headers` fixture is gone. It registered one user per
role and handed out bearer tokens; with no authentication there is nothing to
register and no header to send. Every test now calls the API exactly the way a
real client does.

PostgreSQL: set TEST_DATABASE_URL to a DISPOSABLE database to run the same suite
against the production engine (CI does). SQLite and PostgreSQL disagree on enough
things — timezone-aware timestamps, strict typing — that a suite which only ever
ran on SQLite let a production-only crash through. Every table in that database is
truncated after each test.
"""
import os

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()
if TEST_DATABASE_URL:
    # Must happen before `app` is imported: the engine is built at import time, and
    # the request-telemetry middleware writes through it.
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.models  # noqa: E402  registers every table on Base.metadata
from app.core.database import Base, get_db  # noqa: E402
from app.core.dependencies import rate_limiter, reset_rate_limiter  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def _postgres_engine():
    if not TEST_DATABASE_URL:
        yield None
        return
    from app.core.database import engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session(_postgres_engine):
    if _postgres_engine is not None:
        session = sessionmaker(
            autocommit=False, autoflush=False, bind=_postgres_engine, expire_on_commit=False
        )()
        try:
            yield session
        finally:
            session.rollback()
            session.close()
            tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
            with _postgres_engine.begin() as conn:
                conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        return

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # keeps the SAME in-memory DB across connections
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine, expire_on_commit=False
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass  # db_session owns closing the session

    app.dependency_overrides[get_db] = override_get_db
    # Rate limiting is keyed by client IP, and Starlette's TestClient reports the
    # same fake host for every request — left active, the module-level counter
    # would accumulate across the whole pytest session and start rejecting
    # unrelated later tests with 429s. Rate limiting gets its own dedicated test
    # (test_rate_limiter.py) that does NOT override it.
    app.dependency_overrides[rate_limiter] = lambda: None
    reset_rate_limiter()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture()
def seeded_stock(client):
    """A stock with ~300 bars of history — the minimum useful fixture for
    indicator, signal and portfolio tests."""
    from scripts.generate_synthetic_data import generate_synthetic_ohlcv

    client.post("/api/v1/stocks", json={
        "symbol": "DEMO", "name": "Demo Corp", "exchange": "NSE",
        "market": "IN", "sector": "Technology", "currency": "INR", "market_cap": 250_000,
    })
    df = generate_synthetic_ohlcv(symbol="DEMO", n_days=300, seed=11)
    client.post("/api/v1/stocks/DEMO/prices", json={"bars": [
        {"timestamp": row.timestamp.isoformat(), "open": row.open, "high": row.high,
         "low": row.low, "close": row.close, "volume": row.volume}
        for row in df.itertuples()
    ]})
    return "DEMO"
