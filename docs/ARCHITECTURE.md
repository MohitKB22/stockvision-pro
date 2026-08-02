# Architecture

## Layering

```
HTTP request
    ↓
app/api/v1/endpoints/     Parse, validate, delegate. No business logic, no Session.
    ↓
app/services/             Business logic. Never sees a Request or an HTTP status.
    ↓
app/repositories/         All persistence. The only layer that touches SQLAlchemy.
    ↓
app/models/               ORM definitions.
```

The rule is enforced by what each layer imports. A service raises
`NotFoundException`, not `HTTPException` — which is exactly what lets
`PortfolioService` back an HTTP route, a Celery task and the PDF report generator
without three divergent implementations of the same maths.

`app/domain/` sits beside all of it: enums and the market registry, imported by
both the ORM and the Pydantic schemas so the vocabulary cannot drift between
persistence and API.

## Request lifecycle

1. **RequestContextMiddleware** assigns (or adopts) a correlation ID, publishes it
   to a `ContextVar`, and times the request. Every log line emitted downstream —
   including from deep inside a service that knows nothing about HTTP — carries
   that ID.
2. **SecurityHeadersMiddleware** adds `nosniff`, `DENY`, `Referrer-Policy`.
3. **CORS / GZip** — standard.
4. **Rate limiter** (a router-level dependency) applies a per-IP sliding window,
   honouring `X-Forwarded-For` so one client behind the proxy cannot throttle
   everyone.
5. **The route handler** runs, delegating to a service.
6. **The audit middleware** records method, path, status and duration on a
   separate short-lived session, so a telemetry failure can never poison the
   request's own transaction.

## Error contract

Every non-2xx response has one shape:

```json
{
  "error": {
    "code": "insufficient_data",
    "message": "There is not enough historical data …",
    "status": 422,
    "context": { "symbol": "TCS" },
    "request_id": "8f3c…"
  }
}
```

`code` is stable and machine-readable; `message` is display copy that may be
reworded. The frontend branches on `code` (`ApiError.isEmptyState`), which is why
a "no portfolio yet" 404 renders as an onboarding prompt rather than a red error
box, while a genuine 500 renders as a failure with a request ID to quote.

Four handlers cover the whole surface: domain exceptions, Pydantic validation
errors (reshaped so field errors survive), framework HTTP errors, and a catch-all
that logs the traceback and returns only the request ID.

## Data model

Two ideas do most of the work:

**Orders are the ledger; holdings are a projection.** `PortfolioHolding` is
rebuilt by replaying every `Order` in execution order (`replay_orders`). There is
exactly one code path that answers "what does this portfolio hold", so live order
entry and backtesting cannot diverge. The rebuild is a single bulk delete plus a
single bulk insert inside one transaction.

**Derived values are computed on read.** Current price, returns, indicators, index
levels, 52-week ranges — none are stored. A stored derived value is a value that
eventually goes stale and disagrees with its own source.

Index instruments (NIFTY50, SPX) are ordinary `Stock` rows with `is_index=True`,
so they flow through the identical price and indicator pipeline as any equity
instead of needing a parallel schema.

## Market registry

`app/domain/markets.py` is the single source of truth for everything that differs
between markets: currency, digit grouping (Indian lakh/crore vs western), index
constituents, exchange, benchmark, trading session and timezone.

It is code, not a database table — adding a market needs code anyway, and a table
would force a query on every request for data that cannot change within a deploy.

`GET /api/v1/markets` serves it to the frontend, so the UI's currency symbols and
index lists cannot drift from the backend's.

## ML pipeline

```
OHLCV → build_feature_matrix (33 indicators)
      → walk-forward CV splits          (app/ml/walk_forward.py)
      → Optuna hyperparameter search     (app/ml/train.py)
      → fit final model
      → SHAP importances                 (app/ml/explain.py)
      → persist artifact + MLModel row   (app/ml/registry.py)
```

Models are registered by `{SYMBOL}_{task}` and versioned. The first version for a
symbol+task auto-promotes to production; later ones require an explicit promote,
so a freshly trained but unevaluated model cannot silently start serving.

**The most serious bug fixed in v2**: production-model lookup was scoped by task
only, so a model trained on RELIANCE served predictions for TCS — no error, a
plausible confidence score, entirely wrong. Lookup is now scoped by `(name, task)`
and there is a regression test asserting the cross-symbol request 422s.

## RAG pipeline

```
PDF bytes → pypdf extraction (per page)
          → chunking with overlap
          → hashed embeddings (4096-dim)
          → DocumentEmbedding rows
          ↓  (per query)
question  → embed → FAISS/ChromaDB search → relevance filter
          → LLM (OpenAI/Gemini) or extractive fallback
          → answer + page-level citations
```

The embedding model is a fixed singleton, deliberately *not* swapped based on
whether an API key happens to be set: every chunk must live in the same vector
space as every query, or retrieval breaks silently — a chunk embedded with model A
simply never matches a query embedded with model B, with no error, just wrong
results. The LLM client, by contrast, only affects how retrieved context becomes
prose, so it *is* selected dynamically.

`MIN_RELEVANCE_SCORE = 0.1` is empirically calibrated. At 512 dimensions, hash
collisions made some off-topic queries score higher (0.21) than some genuinely
relevant ones (0.25) — no threshold could separate them. At 4096, collision noise
tops out near 0.055 while real matches sit at 0.19–0.48.

## Frontend

**Server state lives in React Query, keyed centrally.** `lib/query-keys.ts` builds
every key; inline keys are how one file writes `["portfolio", id]`, another
invalidates `["portfolios", id]`, and the resulting stale-data bug survives review.

**The market is context, not a prop.** Every data hook reads it from
`MarketProvider`, so a page cannot request US data while the switcher says India.
Selection persists through `useSyncExternalStore` rather than
`useState` + `useEffect`, which avoids both the cascading render React 19's
compiler flags and the visible flash of the wrong market on load.

**Formatting is centralised and market-driven.** `formatNumber` picks Indian or
western digit grouping from the *market*, not the browser locale — someone in
London looking at NSE data should still see lakhs.

**Charts.** Recharts for analytical charts; a hand-rolled SVG sparkline for the
40+ instances rendered per view (Recharts mounts a ResizeObserver per instance and
at that count it is measurable scroll jank); TradingView's Lightweight Charts for
candlesticks, running locally rather than as an embedded widget so it works in a
network-restricted deployment.

## Deployment

NGINX fronts both the SPA and the API on one origin, which eliminates CORS
preflights entirely. Both Docker images are multi-stage and run as non-root; the
Python runtime image carries no compiler and the Node runtime image carries only
the standalone server output (~180 MB rather than ~1.1 GB).
