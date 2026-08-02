"""
Shared pytest fixtures.

Each test function gets a FRESH in-memory SQLite database (StaticPool-backed so
every connection sees the same DB) — not the dev stockvision.db file — so tests
are isolated from each other and from local state, and can run in any order.

CHANGE LOG (v2.0): the `auth_headers` fixture is gone. It registered one user per
role and handed out bearer tokens; with no authentication there is nothing to
register and no header to send. Every test now calls the API exactly the way a
real client does.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.dependencies import rate_limiter, reset_rate_limiter
from app.main import app


@pytest.fixture()
def db_session():
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
