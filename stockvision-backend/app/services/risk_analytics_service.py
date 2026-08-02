"""
Portfolio Risk Analytics orchestration — new in v2.0.

Splits the DB-aware orchestration (building a value-weighted return series from
holdings, fetching the benchmark, assembling the response) out of the HTTP
layer, where it previously lived inline inside the risk endpoint. That made it
untestable without a TestClient and impossible to reuse from the report
generator, which needs exactly the same numbers.

The pure maths still lives in app/services/risk_service.py; this module only
gets data into the shape those functions expect.
"""
import logging
import uuid

import pandas as pd
from sqlalchemy.orm import Session

from app.core.exceptions import InsufficientDataException, NotFoundException
from app.repositories.market_repository import PriceRepository, StockRepository
from app.repositories.portfolio_repository import HoldingRepository, PortfolioRepository
from app.schemas.portfolio import (
    CorrelationMatrixResponse,
    MonteCarloResponse,
    RiskMetricsResponse,
    StressTestResponse,
)
from app.services import risk_service as rs

logger = logging.getLogger(__name__)


class RiskAnalyticsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.portfolios = PortfolioRepository(db)
        self.holdings = HoldingRepository(db)
        self.prices = PriceRepository(db)
        self.stocks = StockRepository(db)

    # --- Internals ------------------------------------------------------------
    def _holding_returns(
        self, portfolio_id: uuid.UUID, lookback_days: int
    ) -> tuple[dict[str, pd.Series], dict[str, float], float]:
        """
        Returns ({symbol: daily return series}, {symbol: market value}, total).

        One pass, because every caller needs both the per-symbol series (for the
        correlation matrix) and the weights (for the portfolio series).
        """
        portfolio = self.portfolios.get(portfolio_id)
        if not portfolio:
            raise NotFoundException("Portfolio not found")

        holdings = self.holdings.get_for_portfolio(portfolio_id)
        if not holdings:
            raise InsufficientDataException(
                "This portfolio has no holdings, so there is nothing to measure risk on."
            )

        latest = self.prices.get_latest_prices_bulk([h.stock_id for h in holdings])

        series: dict[str, pd.Series] = {}
        values: dict[str, float] = {}
        total = 0.0
        for h in holdings:
            symbol = h.stock.symbol
            price_row = latest.get(h.stock_id)
            value = h.quantity * (price_row.close if price_row else h.average_cost)
            values[symbol] = value
            total += value

            df = self.prices.get_price_series(h.stock_id, limit=lookback_days + 1)
            if len(df) < 2:
                continue
            series[symbol] = df.set_index("timestamp")["close"].pct_change().dropna()

        return series, values, total

    def _portfolio_returns(
        self, portfolio_id: uuid.UUID, lookback_days: int
    ) -> tuple[pd.Series, float]:
        series, values, total = self._holding_returns(portfolio_id, lookback_days)
        if not series:
            raise InsufficientDataException(
                "Not enough price history across this portfolio's holdings to compute risk metrics."
            )

        weighted: pd.Series | None = None
        for symbol, returns in series.items():
            weight = (values.get(symbol, 0.0) / total) if total > 0 else 0.0
            contribution = returns * weight
            weighted = contribution if weighted is None else weighted.add(contribution, fill_value=0)

        if weighted is None or weighted.empty:
            raise InsufficientDataException("Portfolio return series could not be constructed.")
        return weighted, total

    def _benchmark_returns(self, benchmark_symbol: str, lookback_days: int) -> pd.Series | None:
        stock = self.stocks.get_by_symbol(benchmark_symbol)
        if not stock:
            return None
        df = self.prices.get_price_series(stock.id, limit=lookback_days + 1)
        if len(df) < 2:
            return None
        return df.set_index("timestamp")["close"].pct_change().dropna()

    # --- Public API -------------------------------------------------------------
    def metrics(self, portfolio_id: uuid.UUID, lookback_days: int = 252) -> RiskMetricsResponse:
        portfolio = self.portfolios.get(portfolio_id)
        if not portfolio:
            raise NotFoundException("Portfolio not found")

        returns, total_value = self._portfolio_returns(portfolio_id, lookback_days)
        benchmark = self._benchmark_returns(portfolio.benchmark_symbol, lookback_days)

        beta = alpha = None
        if benchmark is not None:
            beta, alpha = rs.beta_alpha(returns, benchmark)

        drawdown = rs.rolling_drawdown_series(returns)

        return RiskMetricsResponse(
            portfolio_id=portfolio_id,
            lookback_days=lookback_days,
            observations=len(returns),
            portfolio_value=total_value,
            annualized_return=rs.annualized_return(returns),
            annualized_volatility=rs.annualized_volatility(returns),
            sharpe_ratio=rs.sharpe_ratio(returns),
            sortino_ratio=rs.sortino_ratio(returns),
            max_drawdown=rs.max_drawdown(returns),
            value_at_risk_95_historical=rs.value_at_risk_historical(returns),
            value_at_risk_95_parametric=rs.value_at_risk_parametric(returns),
            value_at_risk_95_monte_carlo=rs.value_at_risk_monte_carlo(returns),
            expected_shortfall_95=rs.expected_shortfall(returns),
            value_at_risk_amount=rs.value_at_risk_historical(returns) * total_value,
            beta=beta, alpha=alpha,
            benchmark_symbol=portfolio.benchmark_symbol,
            return_distribution=[float(v) for v in returns.tolist()],
            drawdown_series=[{"timestamp": ts, "drawdown": float(v)} for ts, v in drawdown.items()],
        )

    def monte_carlo(
        self, portfolio_id: uuid.UUID, horizon_days: int = 252,
        n_simulations: int = 1_000, lookback_days: int = 252,
    ) -> MonteCarloResponse:
        returns, total_value = self._portfolio_returns(portfolio_id, lookback_days)
        result = rs.monte_carlo_paths(
            returns, horizon_days=horizon_days,
            n_simulations=n_simulations, initial_value=total_value,
        )
        return MonteCarloResponse(portfolio_id=portfolio_id, **result)

    def correlations(self, portfolio_id: uuid.UUID, lookback_days: int = 252) -> CorrelationMatrixResponse:
        series, _, _ = self._holding_returns(portfolio_id, lookback_days)
        result = rs.correlation_matrix(series)
        return CorrelationMatrixResponse(portfolio_id=portfolio_id, lookback_days=lookback_days, **result)

    def stress(self, portfolio_id: uuid.UUID, lookback_days: int = 252) -> StressTestResponse:
        portfolio = self.portfolios.get(portfolio_id)
        if not portfolio:
            raise NotFoundException("Portfolio not found")
        returns, total_value = self._portfolio_returns(portfolio_id, lookback_days)
        benchmark = self._benchmark_returns(portfolio.benchmark_symbol, lookback_days)
        beta = rs.beta_alpha(returns, benchmark)[0] if benchmark is not None else None
        return StressTestResponse(
            portfolio_id=portfolio_id,
            portfolio_value=total_value,
            benchmark_symbol=portfolio.benchmark_symbol,
            scenarios=rs.stress_test(returns, total_value, beta=beta),
        )
