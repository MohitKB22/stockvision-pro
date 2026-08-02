"""
Risk Engine: portfolio and single-series risk metrics.

Design decision: every function here takes a plain pandas Series of *returns*
(not prices, not a DB session) — this is what lets the exact same functions
be unit tested with hand-built series (tests/test_risk_service.py), called
from the live portfolio risk endpoint, AND reused later by the backtesting
engine, without three separate implementations drifting apart.

CHANGE LOG (v2.0): added `monte_carlo_paths`, `correlation_matrix`,
`stress_test` and `rolling_drawdown_series`. The Risk page in the reference
design shows a Monte Carlo fan chart, a correlation matrix and a scenario
table; previously the API returned only scalar metrics, so none of those could
be drawn from real numbers. All four are pure functions like the rest of this
module, and all four are unit tested.
"""
import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def annualized_return(returns: pd.Series) -> float:
    compounded_growth = (1 + returns).prod()
    n_periods = len(returns)
    if n_periods == 0 or compounded_growth <= 0:
        return 0.0
    return float(compounded_growth ** (TRADING_DAYS_PER_YEAR / n_periods) - 1)


def annualized_volatility(returns: pd.Series) -> float:
    return float(returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR))


def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    excess = returns - risk_free_rate / TRADING_DAYS_PER_YEAR
    vol = excess.std()
    # Use an epsilon rather than `vol == 0`: floating-point std() of a
    # constant series can land on a tiny non-zero residual (e.g. ~1e-19)
    # instead of bit-exact 0.0, which would otherwise blow this up into a
    # meaningless ratio of order 1e16 instead of the correct answer, 0.0.
    if vol < 1e-10 or np.isnan(vol):
        return 0.0
    return float((excess.mean() / vol) * np.sqrt(TRADING_DAYS_PER_YEAR))


def sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    """Like Sharpe, but only penalizes downside deviation — an upside swing
    never counts against the ratio, which is the entire point of Sortino."""
    excess = returns - risk_free_rate / TRADING_DAYS_PER_YEAR
    downside = excess[excess < 0]
    downside_std = downside.std()
    if downside_std < 1e-10 or np.isnan(downside_std):
        return 0.0
    return float((excess.mean() / downside_std) * np.sqrt(TRADING_DAYS_PER_YEAR))


def max_drawdown(returns: pd.Series) -> float:
    """Returns a negative number (e.g. -0.23 means a 23% peak-to-trough decline)."""
    wealth_index = (1 + returns).cumprod()
    running_max = wealth_index.cummax()
    drawdown = (wealth_index - running_max) / running_max
    return float(drawdown.min()) if len(drawdown) else 0.0


def value_at_risk_historical(returns: pd.Series, confidence: float = 0.95) -> float:
    """Historical VaR: the empirical loss quantile — no distributional
    assumption, just 'what was the worst X% of days actually like'."""
    if len(returns) == 0:
        return 0.0
    return float(-np.percentile(returns, (1 - confidence) * 100))


def value_at_risk_parametric(returns: pd.Series, confidence: float = 0.95) -> float:
    """Parametric (variance-covariance) VaR assuming normally distributed
    returns — the classic closed-form estimate, fast but sensitive to fat tails."""
    from scipy.stats import norm

    mu, sigma = returns.mean(), returns.std()
    z = norm.ppf(1 - confidence)
    return float(-(mu + z * sigma))


def value_at_risk_monte_carlo(
    returns: pd.Series, confidence: float = 0.95, n_simulations: int = 10_000, seed: int = 42
) -> float:
    """
    Monte Carlo VaR: simulate n_simulations one-day returns by sampling from
    a Normal(mu, sigma) fit to history, then take the empirical loss quantile
    of the simulated distribution. This is deliberately a *different*
    computational path from the parametric formula above (simulation vs.
    closed-form) even though both assume normality — the brief asks for
    Monte Carlo Simulation as its own listed capability, and this is also the
    extension point for swapping in a fatter-tailed or bootstrapped
    simulation later without touching the parametric estimate.
    """
    rng = np.random.default_rng(seed)
    mu, sigma = returns.mean(), returns.std()
    simulated = rng.normal(mu, sigma, n_simulations)
    return float(-np.percentile(simulated, (1 - confidence) * 100))


def expected_shortfall(returns: pd.Series, confidence: float = 0.95) -> float:
    """Expected Shortfall / CVaR: average loss GIVEN that the loss already
    exceeds the VaR threshold — answers 'how bad is bad', not just 'how
    often is bad'."""
    if len(returns) == 0:
        return 0.0
    var_threshold = -value_at_risk_historical(returns, confidence)
    tail_losses = returns[returns <= var_threshold]
    if len(tail_losses) == 0:
        return float(-var_threshold)
    return float(-tail_losses.mean())


def beta_alpha(returns: pd.Series, benchmark_returns: pd.Series, risk_free_rate: float = 0.0) -> tuple[float | None, float | None]:
    """CAPM beta & alpha vs. a benchmark return series (e.g. SPY)."""
    aligned = pd.concat([returns, benchmark_returns], axis=1, join="inner").dropna()
    if len(aligned) < 2:
        return None, None
    r, b = aligned.iloc[:, 0], aligned.iloc[:, 1]
    # np.cov defaults to ddof=1 (sample covariance); np.var defaults to
    # ddof=0 (population variance). Left mismatched, beta(x, x) evaluates to
    # n/(n-1) instead of exactly 1.0 — a small but real systematic bias.
    # Both must use the same ddof.
    covariance = np.cov(r, b, ddof=1)[0, 1]
    benchmark_variance = np.var(b, ddof=1)
    if benchmark_variance == 0:
        return None, None
    beta = covariance / benchmark_variance
    daily_rf = risk_free_rate / TRADING_DAYS_PER_YEAR
    alpha_daily = r.mean() - (daily_rf + beta * (b.mean() - daily_rf))
    alpha_annualized = alpha_daily * TRADING_DAYS_PER_YEAR
    return float(beta), float(alpha_annualized)


# --- v2.0 additions -----------------------------------------------------------
def rolling_drawdown_series(returns: pd.Series) -> pd.Series:
    """Full drawdown path (not just the minimum) — what the underwater chart plots."""
    wealth = (1 + returns).cumprod()
    return (wealth - wealth.cummax()) / wealth.cummax()


def monte_carlo_paths(
    returns: pd.Series,
    *,
    horizon_days: int = 252,
    n_simulations: int = 1_000,
    initial_value: float = 1.0,
    percentiles: tuple[float, ...] = (5, 25, 50, 75, 95),
    seed: int = 42,
) -> dict:
    """
    Geometric Brownian Motion simulation of portfolio value over `horizon_days`.

    Returns the requested percentile bands (the fan chart), a small sample of
    individual paths for visual texture, and terminal-value statistics. Seeded,
    so the same inputs always produce the same chart — a risk figure that
    changes every time you refresh is not a risk figure.

    This shares the normality assumption with `value_at_risk_parametric` and
    therefore understates true tail risk for fat-tailed return series. That is a
    property of GBM, stated here rather than hidden: the extension point for a
    bootstrapped or Student-t simulation is this function alone.
    """
    if len(returns) < 2:
        return {
            "horizon_days": horizon_days, "n_simulations": 0,
            "initial_value": initial_value, "percentiles": {}, "sample_paths": [], "terminal": {},
        }

    rng = np.random.default_rng(seed)
    mu = float(returns.mean())
    sigma = float(returns.std())

    shocks = rng.normal(mu, sigma, size=(n_simulations, horizon_days))
    paths = initial_value * np.cumprod(1 + shocks, axis=1)
    paths = np.hstack([np.full((n_simulations, 1), initial_value), paths])

    bands = {
        f"p{int(p)}": [float(v) for v in np.percentile(paths, p, axis=0)]
        for p in percentiles
    }
    terminal = paths[:, -1]
    return {
        "horizon_days": horizon_days,
        "n_simulations": n_simulations,
        "initial_value": initial_value,
        "percentiles": bands,
        "sample_paths": [[float(v) for v in row] for row in paths[: min(25, n_simulations)]],
        "terminal": {
            "mean": float(terminal.mean()),
            "median": float(np.median(terminal)),
            "std": float(terminal.std()),
            "p5": float(np.percentile(terminal, 5)),
            "p95": float(np.percentile(terminal, 95)),
            "probability_of_loss": float((terminal < initial_value).mean()),
            "expected_return_pct": float(terminal.mean() / initial_value - 1.0),
        },
    }


def correlation_matrix(return_series: dict[str, pd.Series]) -> dict:
    """
    Pairwise Pearson correlation across aligned return series.

    Alignment is an inner join on the date index — correlating series with
    mismatched calendars by POSITION rather than by DATE silently produces a
    meaningless number, which is a classic and hard-to-spot analytics bug.
    """
    labels = [k for k, v in return_series.items() if v is not None and len(v) > 2]
    if len(labels) < 2:
        return {"labels": labels, "matrix": [], "average_correlation": None}

    frame = pd.concat([return_series[k].rename(k) for k in labels], axis=1, join="inner").dropna()
    if len(frame) < 3:
        return {"labels": labels, "matrix": [], "average_correlation": None}

    corr = frame.corr()
    matrix = [[float(corr.iloc[i, j]) for j in range(len(corr))] for i in range(len(corr))]
    off_diagonal = [
        matrix[i][j] for i in range(len(matrix)) for j in range(len(matrix)) if i != j
    ]
    return {
        "labels": list(corr.columns),
        "matrix": matrix,
        "average_correlation": float(np.mean(off_diagonal)) if off_diagonal else None,
    }


# Scenario shocks are an instantaneous market move plus a volatility multiplier.
# Magnitudes are calibrated to the actual historical episodes they are named
# after, so the labels are not decorative.
STRESS_SCENARIOS: dict[str, dict[str, float]] = {
    "2008 Financial Crisis": {"market_shock": -0.42, "volatility_multiplier": 2.8},
    "COVID-19 Crash (Mar 2020)": {"market_shock": -0.34, "volatility_multiplier": 3.2},
    "2022 Rate Shock": {"market_shock": -0.19, "volatility_multiplier": 1.7},
    "Flash Crash (single session)": {"market_shock": -0.09, "volatility_multiplier": 4.0},
    "Sharp Rally": {"market_shock": 0.15, "volatility_multiplier": 1.4},
}


def stress_test(
    returns: pd.Series, portfolio_value: float, beta: float | None = None
) -> list[dict]:
    """
    Applies each named scenario to a portfolio.

    Impact is scaled by beta when one is available (a low-beta portfolio
    genuinely does not take the full index shock); absent a beta we assume 1.0
    AND say so in the payload rather than silently pretending to know.
    """
    effective_beta = beta if beta is not None else 1.0
    base_vol = float(returns.std()) if len(returns) > 1 else 0.0

    results = []
    for name, params in STRESS_SCENARIOS.items():
        shock = params["market_shock"] * effective_beta
        impact_value = portfolio_value * shock
        stressed_vol = base_vol * params["volatility_multiplier"]
        results.append({
            "scenario": name,
            "market_shock_pct": params["market_shock"],
            "portfolio_impact_pct": shock,
            "portfolio_impact_value": impact_value,
            "resulting_value": portfolio_value + impact_value,
            "stressed_daily_volatility": stressed_vol,
            "stressed_annual_volatility": stressed_vol * np.sqrt(TRADING_DAYS_PER_YEAR),
            "beta_used": effective_beta,
            "beta_assumed": beta is None,
        })
    return results
