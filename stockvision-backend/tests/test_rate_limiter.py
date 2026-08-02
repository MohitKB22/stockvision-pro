"""
Rate limiter tests.

Deliberately does NOT use the `client` fixture, which overrides the limiter to a
no-op — this is the one place the real limiter must run.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.dependencies import reset_rate_limiter
from app.main import app


@pytest.fixture()
def limited_client(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 5)
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    reset_rate_limiter()

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    reset_rate_limiter()
    session.close()
    engine.dispose()


class TestRateLimiter:
    def test_requests_under_the_limit_succeed(self, limited_client):
        for _ in range(5):
            assert limited_client.get("/api/v1/stocks").status_code == 200

    def test_exceeding_the_limit_returns_429_with_the_standard_envelope(self, limited_client):
        for _ in range(5):
            limited_client.get("/api/v1/stocks")

        response = limited_client.get("/api/v1/stocks")
        assert response.status_code == 429

        error = response.json()["error"]
        assert error["code"] == "rate_limited"
        # The retry hint is what lets a client back off intelligently instead of
        # hammering — its absence was a real gap in v1.
        assert error["context"]["retry_after_seconds"] >= 1
        assert error["context"]["limit"] == 5

    def test_health_endpoint_is_not_rate_limited(self, limited_client):
        """Liveness probes must never be throttled — a rate-limited /health makes
        an orchestrator kill a perfectly healthy container under load."""
        for _ in range(20):
            assert limited_client.get("/health").status_code == 200

    def test_disabling_the_limiter_is_honoured(self, limited_client, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
        reset_rate_limiter()
        for _ in range(15):
            assert limited_client.get("/api/v1/stocks").status_code == 200
