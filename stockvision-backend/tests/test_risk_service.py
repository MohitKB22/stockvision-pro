import numpy as np
import pandas as pd
import pytest

from app.services import risk_service as rs


class TestSharpeAndSortino:
    def test_zero_volatility_returns_zero_not_infinity(self):
        """A constant-return series has zero std dev -- must return 0.0, not
        divide-by-zero infinity or NaN."""
        flat = pd.Series([0.001] * 100)
        assert rs.sharpe_ratio(flat) == 0.0
        assert rs.sortino_ratio(flat) == 0.0

    def test_higher_mean_return_gives_higher_sharpe(self):
        rng = np.random.default_rng(1)
        low_return = pd.Series(rng.normal(0.0001, 0.01, 500))
        high_return = pd.Series(rng.normal(0.001, 0.01, 500))
        assert rs.sharpe_ratio(high_return) > rs.sharpe_ratio(low_return)

    def test_sortino_ignores_upside_volatility_when_mean_is_held_constant(self):
        """
        Sortino = mean(excess) / downside_deviation. To isolate 'Sortino
        ignores upside VOLATILITY', both series below share (a) identical
        downside days and (b) the identical overall mean — but 'wild' spreads
        its upside across more dispersed values (0.02/0.00 alternating)
        instead of a constant 0.01. Since mean and downside deviation are
        both unchanged, Sortino must be identical. Sharpe, which divides by
        TOTAL volatility, must be lower for 'wild' because its total
        variance is higher even though its mean is not.
        """
        base_downside = [-0.02, -0.01, -0.015, -0.005] * 25  # 100 values, same in both; sums to -1.25
        # Upside sums must be identical (equal means) AND large enough that the
        # overall series mean is clearly positive -- otherwise a negative mean
        # divided by a larger volatility moves *toward* zero (less negative),
        # which inverts the "more volatility -> lower Sharpe" direction we're
        # testing for. Both sum to 3.0 over 100 days.
        calm_upside = [0.03] * 100          # zero dispersion
        wild_upside = [0.06, 0.0] * 50      # same sum/mean, far more dispersed

        calm = pd.Series(base_downside + calm_upside)
        wild = pd.Series(base_downside + wild_upside)

        assert calm.mean() == pytest.approx(wild.mean())  # confirms the construction is valid
        assert calm.mean() > 0  # ensures the Sharpe-direction argument below is unambiguous
        assert rs.sortino_ratio(calm) == pytest.approx(rs.sortino_ratio(wild), rel=1e-9)
        # Sharpe divides the same positive mean by TOTAL volatility, which is
        # genuinely higher for 'wild' -> Sharpe must be lower for 'wild'.
        assert rs.sharpe_ratio(wild) < rs.sharpe_ratio(calm)

    def test_sortino_rewards_higher_mean_even_with_identical_downside(self):
        """
        This is the flip side of the test above and is equally important to
        document: Sortino is NOT insensitive to the *mean* — only to upside
        *volatility*. A series with strictly better upside (higher mean, same
        downside) SHOULD score a higher Sortino. Asserting near-equality here
        would be testing for the wrong invariant.
        """
        base_downside = [-0.02, -0.01, -0.015, -0.005] * 25
        modest_upside = [0.01] * 100
        strong_upside = [0.05] * 100

        modest = pd.Series(base_downside + modest_upside)
        strong = pd.Series(base_downside + strong_upside)

        assert rs.sortino_ratio(strong) > rs.sortino_ratio(modest)


class TestMaxDrawdown:
    def test_known_drawdown_value(self):
        # Prices: 100 -> 110 -> 88 -> 95.  Peak 110, trough 88 => -20% drawdown.
        prices = pd.Series([100, 110, 88, 95.0])
        returns = prices.pct_change().dropna()
        dd = rs.max_drawdown(returns)
        assert dd == pytest.approx(-0.2, abs=1e-6)

    def test_monotonic_gains_have_zero_drawdown(self):
        returns = pd.Series([0.01] * 50)
        assert rs.max_drawdown(returns) == pytest.approx(0.0, abs=1e-9)


class TestValueAtRisk:
    def test_historical_var_matches_manual_percentile(self):
        returns = pd.Series(np.linspace(-0.05, 0.05, 101))  # evenly spaced, easy to hand-check
        var_95 = rs.value_at_risk_historical(returns, confidence=0.95)
        expected = -np.percentile(returns, 5)
        assert var_95 == pytest.approx(expected)

    def test_var_is_non_negative_for_typical_return_series(self):
        rng = np.random.default_rng(3)
        returns = pd.Series(rng.normal(0.0005, 0.02, 1000))
        assert rs.value_at_risk_historical(returns) >= 0
        assert rs.value_at_risk_parametric(returns) >= 0
        assert rs.value_at_risk_monte_carlo(returns) >= 0

    def test_monte_carlo_var_converges_to_parametric_var_for_normal_data(self):
        """Since Monte Carlo VaR samples from a Normal(mu, sigma) fit to the
        same data, with enough simulations it should land close to the
        closed-form parametric estimate."""
        rng = np.random.default_rng(5)
        returns = pd.Series(rng.normal(0.0002, 0.015, 2000))
        parametric = rs.value_at_risk_parametric(returns)
        monte_carlo = rs.value_at_risk_monte_carlo(returns, n_simulations=50_000)
        assert monte_carlo == pytest.approx(parametric, abs=0.01)

    def test_expected_shortfall_is_at_least_as_large_as_var(self):
        """Expected Shortfall (average tail loss) must always be >= VaR
        (the threshold that defines the tail) for any real loss distribution."""
        rng = np.random.default_rng(9)
        returns = pd.Series(rng.normal(0, 0.02, 1000))
        var_95 = rs.value_at_risk_historical(returns, 0.95)
        es_95 = rs.expected_shortfall(returns, 0.95)
        assert es_95 >= var_95


class TestBetaAlpha:
    def test_beta_of_one_for_identical_series(self):
        rng = np.random.default_rng(11)
        benchmark = pd.Series(rng.normal(0.0005, 0.01, 300))
        beta, alpha = rs.beta_alpha(benchmark, benchmark)
        assert beta == pytest.approx(1.0, abs=1e-6)
        assert alpha == pytest.approx(0.0, abs=1e-6)

    def test_beta_scales_linearly(self):
        rng = np.random.default_rng(13)
        benchmark = pd.Series(rng.normal(0.0003, 0.01, 300))
        double_beta_asset = benchmark * 2
        beta, _ = rs.beta_alpha(double_beta_asset, benchmark)
        assert beta == pytest.approx(2.0, abs=1e-6)

    def test_returns_none_for_insufficient_overlap(self):
        short_series = pd.Series([0.01])
        beta, alpha = rs.beta_alpha(short_series, short_series)
        assert beta is None and alpha is None
