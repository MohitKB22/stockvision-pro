# API Reference

Base URL: `/api/v1` · Interactive docs: `/docs` · OpenAPI: `/openapi.json`

**No authentication.** There are no tokens, headers or cookies to send.

## Error envelope

Every non-2xx response:

```json
{ "error": { "code": "not_found", "message": "…", "status": 404, "request_id": "8f3c…" } }
```

Branch on `code`, never on `message`.

| Code | Status | Meaning |
| --- | --- | --- |
| `bad_request` | 400 | Malformed request or a rejected operation |
| `not_found` | 404 | Resource does not exist |
| `no_portfolio` | 404 | No portfolio for this market yet — render onboarding |
| `already_exists` | 409 | Duplicate identifying attribute |
| `validation_error` | 422 | Field errors in `context.fields` |
| `insufficient_data` | 422 | Not enough history to compute |
| `model_not_trained` | 422 | No model for this symbol + task |
| `rate_limited` | 429 | `context.retry_after_seconds` |
| `internal_error` | 500 | Quote `request_id` when reporting |

Every response carries `X-Request-ID` and `X-Response-Time-ms`. An inbound
`X-Request-ID` is preserved, so a trace started at the edge survives into the app.

## Markets

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/markets` | Currency, digit grouping, indices — the UI's source of truth |
| GET | `/market/session` | Open/closed. `holiday_calendar_applied` is always `false` |

## Market data

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/market/overview` | Everything the Market page needs in one call |
| GET | `/market/indices` | `is_synthetic` says whether the level was derived from constituents |
| GET | `/market/indices/{symbol}/constituents` | |
| GET | `/market/movers` | Gainers, losers, most active |
| GET | `/market/sectors` | Cap-weighted, not equal-weighted |
| GET | `/market/heatmap` | Treemap payload: sector, market cap, return |
| GET | `/market/breadth` | Advance/decline, new highs/lows, turnover |
| GET | `/market/52-week` | Near-high and near-low lists |
| GET | `/market/quotes?symbols=A,B,C` | Batch — one request, not N |
| GET | `/market/quotes/{symbol}` | |

Symbols with fewer than two price bars are **omitted**, never shown as 0.00%.

## Instruments

| Method | Path |
| --- | --- |
| GET / POST | `/stocks` |
| GET | `/stocks/search?q=` |
| GET | `/stocks/sectors` |
| GET | `/stocks/{symbol}` |
| GET / POST | `/stocks/{symbol}/prices` |
| GET | `/stocks/{symbol}/features` |

`POST /stocks/{symbol}/prices` is idempotent — duplicate `(symbol, timestamp)`
pairs are skipped, so re-submitting the same CSV is always safe.

## Portfolio

| Method | Path | Notes |
| --- | --- | --- |
| GET / POST | `/portfolios` | |
| GET | `/portfolios/default` | 404 `no_portfolio` when none exists |
| GET / PATCH / DELETE | `/portfolios/{id}` | |
| GET | `/portfolios/{id}/summary` | Holdings, P&L, allocation |
| GET | `/portfolios/{id}/performance` | Constant-holdings valuation series |
| GET | `/portfolios/{id}/transactions` | |
| POST | `/portfolios/{id}/orders` | Selling more than held → 400 |

## Risk

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/portfolios/{id}/risk` | VaR ×3, Sharpe, Sortino, drawdown, beta/alpha |
| GET | `/portfolios/{id}/risk/monte-carlo` | Seeded — deterministic for a given portfolio |
| GET | `/portfolios/{id}/risk/correlation` | Aligned by date, not by position |
| GET | `/portfolios/{id}/risk/stress-test` | `beta_assumed` flags when beta was not computable |

## ML & signals

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/models` | Registry |
| POST | `/models/train` | Synchronous; seconds on seeded data |
| POST | `/models/{id}/promote` | |
| POST | `/predictions` | Scoped by symbol — a model cannot serve another symbol |
| GET | `/predictions/{symbol}/history` | `correct: null` = not yet verifiable |
| GET | `/predictions/{symbol}/forecast` | `model_informed` says whether a model contributed |
| GET | `/signals/recent` | Declared before `/signals/{symbol}` so it is not shadowed |
| POST | `/signals` | Bulk; failures are skipped, not fatal |
| POST | `/signals/{symbol}` | |

## Copilot

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/documents/upload` | PDF only, 25 MB cap |
| GET / DELETE | `/documents` · `/documents/{id}` | |
| GET | `/copilot/prompts` | |
| GET / POST / DELETE | `/copilot/conversations…` | |
| POST | `/copilot/query` | `llm_provider` names what produced the answer |
| POST | `/copilot/query/stream` | SSE: `start` → `token`… → `done` |
| GET | `/copilot/history` | |

## News, watchlist, reports, settings, admin

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/news` · `/news/sentiment` | `summary.engine` names the scoring engine |
| GET / POST / DELETE | `/watchlists…` | Default list is created on first read |
| GET / POST / DELETE | `/reports` · `/reports/generate` · `/reports/{id}/download` | |
| GET / PATCH / POST | `/settings` · `/settings/reset` | Unknown keys are dropped |
| GET | `/settings/integrations` | Status only — never key material |
| GET | `/admin/overview` · `/admin/health` · `/admin/logs` | `change_pct: null` ≠ 0% |

## Conventions

- `limit` is hard-capped at 500 on list endpoints (uncapped `limit` is a trivial DoS).
- All percentages are **ratios** (`0.0521` = 5.21%).
- All timestamps are ISO-8601 UTC.
