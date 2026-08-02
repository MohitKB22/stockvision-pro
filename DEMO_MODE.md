# Demo mode

Demo mode lets the frontend run with no backend at all. It exists because the
Next.js app deploys to Vercel and the FastAPI service does not, and a deployed
frontend showing "Cannot reach the API" on every card is a bad advertisement for
an application that is otherwise complete.

Turn it on with `NEXT_PUBLIC_DEMO_MODE=true` (already set for production builds
in `stockvision-frontend/.env.production`).

## How it works

One seam, in `src/lib/api.ts`:

```ts
if (IS_DEMO) {
  installDemoAdapter(api);
}
```

That replaces axios's **adapter** — the piece that actually performs the
request. Nothing else in the app changes. Every hook, query key, retry policy,
error envelope and empty-state code runs exactly as it does against the real
backend; requests simply never leave the page.

This was chosen over mocking the React Query hooks for a specific reason: mocked
hooks bypass the data layer, so the demo would prove nothing about it. Swapping
the adapter exercises the real one, including the `ApiError` normalization and
the `model_not_trained` / `not_found` empty-state paths.

```
src/lib/demo/
├── rng.ts         seeded PRNG, gaussian draws, percentile / correlation helpers
├── catalog.ts     the universe — mirrors scripts/seed_data.py exactly
├── series.ts      synthetic OHLCV + RSI, MACD, Bollinger, ATR, ADX, volatility
├── world.ts       instruments, indices, portfolios, ledgers, mutable stores
├── analytics.ts   quotes, aggregates, VaR / Sharpe / beta / Monte Carlo / signals
├── routes.ts      65 endpoint handlers and the path matcher
└── index.ts       the axios adapter, and browser-side report generation
```

Deleting this directory and the two lines that reference it removes demo mode
completely, leaving no trace in any component.

## What is generated and what is real

**Generated:** the price history. Geometric Brownian motion with regime-switching
volatility and a shared market factor per market, seeded deterministically — the
same model `stockvision-backend/scripts/generate_synthetic_data.py` uses. The
symbols, names, sectors, market caps, index constituents, starting positions and
news corpus are copied from `scripts/seed_data.py`, so the demo shows the same
universe a seeded backend would.

**Real:** the analytics computed on that history. Historical, parametric and
Monte Carlo VaR; expected shortfall; Sharpe and Sortino; maximum drawdown; beta
and alpha regressed against the benchmark index; the correlation matrix; the
Monte Carlo fan chart; Wilder's RSI and ATR; MACD; Bollinger bands; ADX with
directional movement. These are the actual calculations, which is why the
numbers stay consistent with each other when you poke at them.

The market factor matters more than it sounds: without a shared factor every
symbol is an independent random walk, the correlation matrix comes out near zero
everywhere and portfolio beta lands around 0.3. With it, cross-sectional
correlations sit in the 0.3–0.6 range and drawdowns are market-wide.

**Honest limits**, stated in the UI as well as here:

- The copilot answers from a small canned corpus via the extractive fallback
  engine. Uploading a PDF indexes its real filename, size and page estimate, but
  the answer text is not generated from your file.
- Reports are assembled in the browser. The PDF is a genuine, valid PDF and the
  CSV opens in a spreadsheet — they describe the demo dataset rather than a
  persisted portfolio.
- Mutations (orders, watchlist edits, training a model, settings) are held in
  memory. They behave correctly for the session and reset on reload.
- The world is built once per page load, so prices do not twitch between
  React Query refetches — the same stability a database would give.

## Trying the interactive paths

1. **Prediction → Train a Model → RELIANCE.** Asking for a prediction on a symbol
   with no registered model returns `model_not_trained`, and the UI shows the
   neutral "train one first" state rather than a red error — the real empty-state
   contract. Train it, then predict.
2. **Portfolio → New Order.** Buying updates the holding's average cost, the cash
   balance, the weights and the ledger. Selling more than you hold is rejected
   with a 422, as it should be.
3. **Market switcher IN ⇄ US.** Two independent worlds, each with its own market
   factor, currency and digit grouping (₹12,45,000 vs $1,245,000).
