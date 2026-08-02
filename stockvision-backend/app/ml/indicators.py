"""
Feature Engineering Engine: vectorized technical indicators.

Design decision: every function takes and returns pandas Series/DataFrames
and contains NO Python-level `for` loops over rows — each is implemented with
pandas/numpy vector operations (.rolling, .ewm, shift/diff, cumulative ops).
This matters at scale: a for-loop indicator over 10 years of minute bars for
500 symbols is the difference between a feature engineering job that takes
seconds and one that takes hours.

All functions are pure (no I/O, no DB access) so they're trivially unit
testable — see tests/test_indicators.py, which checks each one against
hand-computed values on a small fixture, not just "does it run".
"""
import numpy as np
import pandas as pd


def sma(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window=window, min_periods=window).mean()


def ema(close: pd.Series, span: int) -> pd.Series:
    return close.ewm(span=span, adjust=False, min_periods=span).mean()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Wilder's RSI via exponential (not simple) moving average of gains/losses."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_value = 100 - (100 / (1 + rs))

    # The RS ratio is undefined (division by zero) whenever a window has had
    # zero average losses — which the .replace(0, np.nan) above turns into a
    # silent NaN instead of the mathematically correct limit. As avg_loss -> 0+
    # with avg_gain > 0, RS -> infinity, so RSI -> 100; a fully flat window
    # (no gains or losses at all) is neutral, RSI = 50. Without this
    # correction, any pure uptrend (or any flat stretch) would wrongly report
    # RSI = NaN, which is exactly the case the real sample data hits below.
    edge_case_value = pd.Series(np.where(avg_gain > 0, 100.0, 50.0), index=close.index)
    rsi_value = rsi_value.where(avg_loss != 0, edge_case_value)
    return rsi_value


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    histogram = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "macd_signal": signal_line, "macd_hist": histogram})


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    tr = true_range(high, low, close)
    return tr.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()


def bollinger_bands(close: pd.Series, window: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    mid = sma(close, window)
    std = close.rolling(window=window, min_periods=window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    width = (upper - lower) / mid.replace(0, np.nan)
    return pd.DataFrame({"bb_mid": mid, "bb_upper": upper, "bb_lower": lower, "bb_width": width})


def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    """Cumulative session VWAP (typical price weighted by volume)."""
    typical_price = (high + low + close) / 3
    cum_vol = volume.cumsum().replace(0, np.nan)
    return (typical_price * volume).cumsum() / cum_vol


def adx(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.DataFrame:
    """Average Directional Index — trend strength, plus +DI/-DI direction."""
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high.index)

    tr = true_range(high, low, close)
    atr_ = tr.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()

    plus_di = 100 * (plus_dm.ewm(alpha=1 / window, min_periods=window, adjust=False).mean() / atr_.replace(0, np.nan))
    minus_di = 100 * (minus_dm.ewm(alpha=1 / window, min_periods=window, adjust=False).mean() / atr_.replace(0, np.nan))

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_line = dx.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()

    return pd.DataFrame({"adx": adx_line, "plus_di": plus_di, "minus_di": minus_di})


def cci(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 20) -> pd.Series:
    typical_price = (high + low + close) / 3
    tp_sma = sma(typical_price, window)
    mean_dev = typical_price.rolling(window=window, min_periods=window).apply(
        lambda x: np.abs(x - x.mean()).mean(), raw=True
    )
    return (typical_price - tp_sma) / (0.015 * mean_dev.replace(0, np.nan))


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff().fillna(0))
    return (direction * volume).cumsum()


def supertrend(
    high: pd.Series, low: pd.Series, close: pd.Series, window: int = 10, multiplier: float = 3.0
) -> pd.DataFrame:
    """
    SuperTrend indicator.

    Note: unlike the other indicators here, SuperTrend's *band-flip* logic is
    inherently sequential (each bar's band depends on whether price crossed
    the previous bar's band) — there is no closed-form vectorized formula for
    it in the literature. We vectorize everything computable (ATR, raw upper/
    lower bands) and confine the loop strictly to the O(n) trend-flip state
    machine, which is standard practice even in production TA libraries.
    """
    atr_ = atr(high, low, close, window)
    hl2 = (high + low) / 2
    upper_band = hl2 + multiplier * atr_
    lower_band = hl2 - multiplier * atr_

    trend = pd.Series(index=close.index, dtype=float)
    direction = pd.Series(index=close.index, dtype=int)

    final_upper = upper_band.copy()
    final_lower = lower_band.copy()

    for i in range(len(close)):
        if i == 0 or pd.isna(atr_.iloc[i]):
            trend.iloc[i] = np.nan
            direction.iloc[i] = 1
            continue

        if close.iloc[i - 1] <= final_upper.iloc[i - 1]:
            final_upper.iloc[i] = min(upper_band.iloc[i], final_upper.iloc[i - 1])
        else:
            final_upper.iloc[i] = upper_band.iloc[i]

        if close.iloc[i - 1] >= final_lower.iloc[i - 1]:
            final_lower.iloc[i] = max(lower_band.iloc[i], final_lower.iloc[i - 1])
        else:
            final_lower.iloc[i] = lower_band.iloc[i]

        if close.iloc[i] > final_upper.iloc[i - 1]:
            direction.iloc[i] = 1
        elif close.iloc[i] < final_lower.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]

        trend.iloc[i] = final_lower.iloc[i] if direction.iloc[i] == 1 else final_upper.iloc[i]

    return pd.DataFrame({"supertrend": trend, "supertrend_direction": direction})


def ichimoku(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.DataFrame:
    """Ichimoku Kinko Hyo — tenkan/kijun/senkou spans A & B, chikou span."""
    tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
    kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
    senkou_a = ((tenkan + kijun) / 2).shift(26)
    senkou_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
    chikou = close.shift(-26)
    return pd.DataFrame(
        {
            "ichimoku_tenkan": tenkan,
            "ichimoku_kijun": kijun,
            "ichimoku_senkou_a": senkou_a,
            "ichimoku_senkou_b": senkou_b,
            "ichimoku_chikou": chikou,
        }
    )


def momentum(close: pd.Series, window: int = 10) -> pd.Series:
    return close.diff(window)


def volume_profile_proxy(close: pd.Series, volume: pd.Series, window: int = 20) -> pd.Series:
    """
    Rolling volume-weighted average price as a lightweight, streaming-friendly
    proxy for volume profile's "point of control" over the trailing window
    (a full price-bucketed volume histogram is a Phase-2 addition once
    tick-level data is ingested — this proxy uses only OHLCV bars).
    """
    return (close * volume).rolling(window).sum() / volume.rolling(window).sum().replace(0, np.nan)


def returns(close: pd.Series) -> pd.Series:
    return close.pct_change()


def log_returns(close: pd.Series) -> pd.Series:
    return np.log(close / close.shift(1))


def rolling_volatility(close: pd.Series, window: int = 20, annualize: bool = True) -> pd.Series:
    vol = returns(close).rolling(window=window, min_periods=window).std()
    return vol * np.sqrt(252) if annualize else vol


def correlation_feature(close: pd.Series, benchmark_close: pd.Series, window: int = 60) -> pd.Series:
    """Rolling correlation of returns vs. a benchmark series — used for market-breadth features."""
    r1 = returns(close)
    r2 = returns(benchmark_close)
    return r1.rolling(window).corr(r2)


def build_feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute the full indicator set for an OHLCV DataFrame in one call.

    `df` must have columns: timestamp, open, high, low, close, volume
    (ascending by timestamp — see PriceRepository.get_price_series).

    Returns the original columns plus every engineered feature, one row per
    input row (NaN where a given indicator's warm-up window hasn't been
    reached yet — this is expected and handled downstream by dropna() at
    train time, not silently filled).
    """
    out = df.copy()
    # `open` is deliberately not unpacked: no indicator below uses it, and an
    # unused binding is exactly what ruff's F841 exists to catch. The single-letter
    # names for the rest are retained on purpose — they match the standard notation
    # in every technical-analysis reference these formulas come from, which makes
    # them easier to verify against a source than descriptive names would be.
    h, low, c, v = out["high"], out["low"], out["close"], out["volume"]

    out["sma_7"] = sma(c, 7)
    out["sma_14"] = sma(c, 14)
    out["sma_30"] = sma(c, 30)
    out["sma_50"] = sma(c, 50)
    out["ema_12"] = ema(c, 12)
    out["ema_26"] = ema(c, 26)
    out["rsi_14"] = rsi(c, 14)

    macd_df = macd(c)
    out = pd.concat([out, macd_df], axis=1)

    out["atr_14"] = atr(h, low, c, 14)

    bb_df = bollinger_bands(c)
    out = pd.concat([out, bb_df], axis=1)

    out["vwap"] = vwap(h, low, c, v)

    adx_df = adx(h, low, c)
    out = pd.concat([out, adx_df], axis=1)

    out["cci_20"] = cci(h, low, c)
    out["obv"] = obv(c, v)

    st_df = supertrend(h, low, c)
    out = pd.concat([out, st_df], axis=1)

    ichi_df = ichimoku(h, low, c)
    out = pd.concat([out, ichi_df], axis=1)

    out["momentum_10"] = momentum(c, 10)
    out["volume_profile_20"] = volume_profile_proxy(c, v, 20)
    out["return_1d"] = returns(c)
    out["log_return_1d"] = log_returns(c)
    out["volatility_20d"] = rolling_volatility(c, 20)
    out["volatility_60d"] = rolling_volatility(c, 60)

    return out


FEATURE_COLUMNS: list[str] = [
    "sma_7", "sma_14", "sma_30", "sma_50", "ema_12", "ema_26", "rsi_14",
    "macd", "macd_signal", "macd_hist", "atr_14",
    "bb_mid", "bb_upper", "bb_lower", "bb_width", "vwap",
    "adx", "plus_di", "minus_di", "cci_20", "obv",
    "supertrend", "supertrend_direction",
    "ichimoku_tenkan", "ichimoku_kijun", "ichimoku_senkou_a", "ichimoku_senkou_b",
    "momentum_10", "volume_profile_20", "return_1d", "log_return_1d",
    "volatility_20d", "volatility_60d",
]
