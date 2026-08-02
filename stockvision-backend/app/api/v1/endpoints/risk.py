"""
Risk Engine endpoints.

CHANGE LOG (v2.0): the value-weighted return-series construction that used to
live inline in this module moved into app/services/risk_analytics_service.py — it
was ~50 lines of financial maths inside an HTTP handler, untestable without a
TestClient and impossible to reuse from the report generator that needs identical
numbers. Monte Carlo, correlation and stress endpoints added.
"""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.portfolio import (
    CorrelationMatrixResponse,
    MonteCarloResponse,
    RiskMetricsResponse,
    StressTestResponse,
)
from app.services.risk_analytics_service import RiskAnalyticsService

router = APIRouter(prefix="/portfolios", tags=["Risk Engine"])


@router.get("/{portfolio_id}/risk", response_model=RiskMetricsResponse,
            summary="VaR, Sharpe, Sortino, drawdown, beta/alpha")
def get_portfolio_risk(
    portfolio_id: uuid.UUID,
    lookback_days: int = Query(default=252, ge=30, le=2000),
    db: Session = Depends(get_db),
):
    return RiskAnalyticsService(db).metrics(portfolio_id, lookback_days=lookback_days)


@router.get("/{portfolio_id}/risk/monte-carlo", response_model=MonteCarloResponse,
            summary="Monte Carlo simulation")
def monte_carlo(
    portfolio_id: uuid.UUID,
    horizon_days: int = Query(default=252, ge=5, le=1260),
    n_simulations: int = Query(default=1000, ge=100, le=20_000),
    lookback_days: int = Query(default=252, ge=30, le=2000),
    db: Session = Depends(get_db),
):
    """Seeded — the same portfolio always produces the same fan chart."""
    return RiskAnalyticsService(db).monte_carlo(
        portfolio_id, horizon_days=horizon_days,
        n_simulations=n_simulations, lookback_days=lookback_days,
    )


@router.get("/{portfolio_id}/risk/correlation", response_model=CorrelationMatrixResponse,
            summary="Holding correlation matrix")
def correlation(
    portfolio_id: uuid.UUID,
    lookback_days: int = Query(default=252, ge=30, le=2000),
    db: Session = Depends(get_db),
):
    return RiskAnalyticsService(db).correlations(portfolio_id, lookback_days=lookback_days)


@router.get("/{portfolio_id}/risk/stress-test", response_model=StressTestResponse,
            summary="Historical scenario stress test")
def stress_test(
    portfolio_id: uuid.UUID,
    lookback_days: int = Query(default=252, ge=30, le=2000),
    db: Session = Depends(get_db),
):
    return RiskAnalyticsService(db).stress(portfolio_id, lookback_days=lookback_days)
