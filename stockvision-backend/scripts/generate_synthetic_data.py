"""
Synthetic OHLCV generator — FOR LOCAL DEVELOPMENT / TESTING ONLY.

This sandbox has no network access to Yahoo Finance / Polygon / Alpha
Vantage / NSE (see app/services/market_data_providers.py for the real
client implementations, which need a reachable network + API keys to run).
To still exercise and demonstrate the feature-engineering and ML training
pipeline end-to-end, this script simulates a daily OHLCV series using
geometric Brownian motion with a mild mean-reverting volatility regime.

This data is NOT real market history. It exists so `scripts/train_model.py`
and the test suite have something realistic-shaped to run against. Swapping
in `MarketDataService.load_historical(symbol)` (real provider) instead of
this generator requires no other code changes — both produce the same
[timestamp, open, high, low, close, volume] DataFrame shape.
"""
import numpy as np
import pandas as pd


def generate_synthetic_ohlcv(
    symbol: str = "SYN",
    n_days: int = 900,
    start_price: float = 150.0,
    annual_drift: float = 0.08,
    annual_vol: float = 0.28,
    seed: int = 7,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dt = 1 / 252

    # Volatility regime-switching: alternate between calm and turbulent
    # stretches so RSI/ADX/SuperTrend see genuine trend AND chop, not just
    # one flavor of price action.
    n_regimes = max(n_days // 60, 1)
    regime_vol = rng.choice([0.6, 1.0, 1.8], size=n_regimes, p=[0.35, 0.45, 0.2])
    vol_path = np.repeat(regime_vol, int(np.ceil(n_days / n_regimes)))[:n_days] * annual_vol

    daily_drift = annual_drift * dt
    shocks = rng.normal(0, 1, n_days) * vol_path * np.sqrt(dt)
    log_returns = daily_drift + shocks
    close = start_price * np.exp(np.cumsum(log_returns))

    # Derive open/high/low from close with realistic intraday behavior:
    # open gaps slightly from prior close; high/low bracket the open-close range.
    open_ = np.empty(n_days)
    open_[0] = start_price
    open_[1:] = close[:-1] * (1 + rng.normal(0, 0.002, n_days - 1))

    intraday_range = np.abs(rng.normal(0, 1, n_days)) * vol_path * close * np.sqrt(dt) * 0.6
    high = np.maximum(open_, close) + intraday_range
    low = np.minimum(open_, close) - intraday_range
    low = np.maximum(low, 0.01)  # price floor safety

    base_volume = rng.integers(2_000_000, 8_000_000, n_days).astype(float)
    volume = base_volume * (1 + np.abs(shocks) * 3)  # volume spikes with volatility

    dates = pd.bdate_range("2021-01-04", periods=n_days)

    return pd.DataFrame(
        {
            "timestamp": dates,
            "open": open_.round(2),
            "high": high.round(2),
            "low": low.round(2),
            "close": close.round(2),
            "volume": volume.round(0),
        }
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="DEMO")
    parser.add_argument("--days", type=int, default=900)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    df = generate_synthetic_ohlcv(symbol=args.symbol, n_days=args.days, seed=args.seed)
    out_path = args.out or f"data/synthetic_{args.symbol.lower()}.csv"
    df.to_csv(out_path, index=False)
    print(f"Wrote {len(df)} synthetic rows to {out_path}")
    print(df.head())
    print("...")
    print(df.tail())
