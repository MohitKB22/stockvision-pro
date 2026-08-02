import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import Market, OrderSide, OrderStatus


# --- Portfolio -------------------------------------------------------------
class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    market: Market = Market.INDIA
    base_currency: str = "INR"
    benchmark_symbol: str = "NIFTY50"
    cash_balance: float = Field(default=0.0, ge=0)


class PortfolioUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    benchmark_symbol: str | None = None
    cash_balance: float | None = Field(default=None, ge=0)
    is_default: bool | None = None


class PortfolioPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    market: Market
    base_currency: str
    benchmark_symbol: str
    cash_balance: float
    is_default: bool
    created_at: datetime


# --- Orders / transactions -------------------------------------------------------
class OrderCreate(BaseModel):
    symbol: str
    side: OrderSide
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    transaction_cost: float = Field(default=0.0, ge=0)
    slippage: float = Field(default=0.0, ge=0)
    notes: str | None = Field(default=None, max_length=500)
    executed_at: datetime | None = Field(
        default=None, description="Defaults to now. Set explicitly to backfill history."
    )


class TransactionPublic(BaseModel):
    id: uuid.UUID
    symbol: str
    name: str
    side: OrderSide
    quantity: float
    price: float
    value: float
    transaction_cost: float
    slippage: float
    status: OrderStatus
    is_simulated: bool
    notes: str | None
    executed_at: datetime


# --- Holdings / summary ------------------------------------------------------------
class HoldingPublic(BaseModel):
    stock_id: uuid.UUID
    symbol: str
    name: str
    sector: str | None
    quantity: float
    average_cost: float
    current_price: float
    previous_close: float
    market_value: float
    cost_basis: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    realized_pnl: float
    day_change: float
    day_change_pct: float
    weight_pct: float


class AllocationSlice(BaseModel):
    label: str
    value: float
    weight_pct: float


class PerformancePoint(BaseModel):
    timestamp: datetime
    value: float
    return_pct: float


class PortfolioSummary(BaseModel):
    portfolio_id: uuid.UUID
    name: str
    market: Market
    base_currency: str
    benchmark_symbol: str
    cash_balance: float
    total_market_value: float
    total_value: float
    total_cost_basis: float
    total_unrealized_pnl: float
    total_unrealized_pnl_pct: float
    total_realized_pnl: float
    day_change: float
    day_change_pct: float
    holding_count: int
    holdings: list[HoldingPublic]
    sector_exposure: list[AllocationSlice]
    asset_allocation: list[AllocationSlice]


# --- Risk ---------------------------------------------------------------------------
class DrawdownPoint(BaseModel):
    timestamp: datetime
    drawdown: float


class RiskMetricsResponse(BaseModel):
    portfolio_id: uuid.UUID
    lookback_days: int
    observations: int
    portfolio_value: float
    annualized_return: float
    annualized_volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    value_at_risk_95_historical: float
    value_at_risk_95_parametric: float
    value_at_risk_95_monte_carlo: float
    expected_shortfall_95: float
    value_at_risk_amount: float
    beta: float | None
    alpha: float | None
    benchmark_symbol: str
    return_distribution: list[float] = Field(
        default_factory=list, description="Raw daily returns — the VaR histogram is drawn from these."
    )
    drawdown_series: list[DrawdownPoint] = Field(default_factory=list)


class MonteCarloTerminal(BaseModel):
    mean: float
    median: float
    std: float
    p5: float
    p95: float
    probability_of_loss: float
    expected_return_pct: float


class MonteCarloResponse(BaseModel):
    portfolio_id: uuid.UUID
    horizon_days: int
    n_simulations: int
    initial_value: float = 0.0
    percentiles: dict[str, list[float]] = Field(default_factory=dict)
    sample_paths: list[list[float]] = Field(default_factory=list)
    terminal: MonteCarloTerminal | dict = Field(default_factory=dict)


class CorrelationMatrixResponse(BaseModel):
    portfolio_id: uuid.UUID
    lookback_days: int
    labels: list[str]
    matrix: list[list[float]]
    average_correlation: float | None


class StressScenario(BaseModel):
    scenario: str
    market_shock_pct: float
    portfolio_impact_pct: float
    portfolio_impact_value: float
    resulting_value: float
    stressed_daily_volatility: float
    stressed_annual_volatility: float
    beta_used: float
    beta_assumed: bool = Field(
        description="True when no benchmark beta was computable and 1.0 was assumed."
    )


class StressTestResponse(BaseModel):
    portfolio_id: uuid.UUID
    portfolio_value: float
    benchmark_symbol: str
    scenarios: list[StressScenario]
