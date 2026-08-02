"""
Unit tests for app/ml/indicators.py.

These check *correctness against known behavior*, not just "does it run
without throwing" — e.g. RSI on a monotonic series must equal exactly 100 or
0, Bollinger bands must always nest upper >= mid >= lower, etc.
"""
import numpy as np
import pandas as pd
import pytest

from app.ml.indicators import (
    atr,
    bollinger_bands,
    build_feature_matrix,
    macd,
    obv,
    rsi,
    sma,
    true_range,
)


@pytest.fixture
def monotonic_up():
    return pd.Series(np.arange(100, 120, 1.0))


@pytest.fixture
def monotonic_down():
    return pd.Series(np.arange(120, 100, -1.0))


@pytest.fixture
def ohlcv_fixture():
    """20 bars of synthetic-but-internally-consistent OHLCV data (high >= max(open,close),
    low <= min(open,close)) so structural indicator invariants can be checked."""
    rng = np.random.default_rng(42)
    n = 60
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    open_ = close + rng.normal(0, 0.3, n)
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 0.5, n))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 0.5, n))
    volume = rng.integers(1_000_000, 5_000_000, n).astype(float)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="D"),
            "open": open_, "high": high, "low": low, "close": close, "volume": volume,
        }
    )


class TestRSI:
    def test_monotonic_up_hits_100(self, monotonic_up):
        result = rsi(monotonic_up, window=14)
        assert result.iloc[-1] == pytest.approx(100.0)

    def test_monotonic_down_hits_0(self, monotonic_down):
        result = rsi(monotonic_down, window=14)
        assert result.iloc[-1] == pytest.approx(0.0)

    def test_flat_series_is_neutral_50(self):
        flat = pd.Series([100.0] * 20)
        result = rsi(flat, window=14)
        assert result.iloc[-1] == pytest.approx(50.0)

    def test_bounded_0_to_100(self, ohlcv_fixture):
        result = rsi(ohlcv_fixture["close"], window=14)
        valid = result.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_warmup_period_is_nan(self, monotonic_up):
        result = rsi(monotonic_up, window=14)
        assert result.iloc[:13].isna().all()


class TestMACD:
    def test_histogram_equals_macd_minus_signal(self, ohlcv_fixture):
        result = macd(ohlcv_fixture["close"])
        diff = (result["macd"] - result["macd_signal"] - result["macd_hist"]).dropna()
        assert np.allclose(diff, 0, atol=1e-9)


class TestBollingerBands:
    def test_band_ordering(self, ohlcv_fixture):
        result = bollinger_bands(ohlcv_fixture["close"])
        valid = result.dropna()
        assert (valid["bb_upper"] >= valid["bb_mid"]).all()
        assert (valid["bb_mid"] >= valid["bb_lower"]).all()

    def test_mid_band_equals_sma(self, ohlcv_fixture):
        bb = bollinger_bands(ohlcv_fixture["close"], window=20)
        sma_20 = sma(ohlcv_fixture["close"], window=20)
        assert np.allclose(bb["bb_mid"].dropna(), sma_20.dropna())


class TestATR:
    def test_true_range_non_negative(self, ohlcv_fixture):
        tr = true_range(ohlcv_fixture["high"], ohlcv_fixture["low"], ohlcv_fixture["close"])
        assert (tr.dropna() >= 0).all()

    def test_atr_non_negative(self, ohlcv_fixture):
        result = atr(ohlcv_fixture["high"], ohlcv_fixture["low"], ohlcv_fixture["close"])
        assert (result.dropna() >= 0).all()


class TestOBV:
    def test_obv_increases_on_up_day(self):
        close = pd.Series([10.0, 11.0])  # price went up
        volume = pd.Series([100.0, 100.0])
        result = obv(close, volume)
        assert result.iloc[1] > result.iloc[0]

    def test_obv_decreases_on_down_day(self):
        close = pd.Series([10.0, 9.0])  # price went down
        volume = pd.Series([100.0, 100.0])
        result = obv(close, volume)
        assert result.iloc[1] < result.iloc[0]


class TestBuildFeatureMatrix:
    def test_output_row_count_matches_input(self, ohlcv_fixture):
        feat = build_feature_matrix(ohlcv_fixture)
        assert len(feat) == len(ohlcv_fixture)

    def test_original_columns_preserved(self, ohlcv_fixture):
        feat = build_feature_matrix(ohlcv_fixture)
        for col in ["timestamp", "open", "high", "low", "close", "volume"]:
            assert col in feat.columns

    def test_no_lookahead_bias_in_final_row(self, ohlcv_fixture):
        """
        Truncating the series to N rows must produce the same indicator
        values at row N-1 as computing on the full series and looking at
        row N-1 — i.e. no indicator is allowed to peek at future rows.
        (ichimoku's senkou spans are intentionally excluded: they are
        *plotted* forward by convention, which is expected, documented
        forward-shifting, not lookahead leakage.)
        """
        full = build_feature_matrix(ohlcv_fixture)
        truncated = build_feature_matrix(ohlcv_fixture.iloc[:40].reset_index(drop=True))
        cols_to_check = [c for c in truncated.columns if not c.startswith("ichimoku")]
        pd.testing.assert_frame_equal(
            full.iloc[:40][cols_to_check].reset_index(drop=True),
            truncated[cols_to_check],
            check_exact=False,
            rtol=1e-6,
        )
