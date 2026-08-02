# Changelog

## v2.0.0 — Modernization

### Removed: the entire authentication subsystem

Deleted `auth.py` (endpoints, schemas, service), `security.py`, the `User` model,
`UserRepository`, every RBAC guard, and the frontend's login page, register page,
auth guard, auth store and the `auto-auth.ts` shim that had been silently logging
every visitor in as a seeded demo admin.

Dropped from the schema: the `users` table, `portfolios.owner_id`,
`documents.uploaded_by`, `audit_logs.user_id`, `copilot_queries.user_id`.

Dropped from dependencies: `python-jose`, `passlib`, `bcrypt`, `email-validator`.

A CI step now greps for any of it returning.

### Fixed

| Bug | Impact |
| --- | --- |
| Production-model lookup scoped by task only | A model trained on RELIANCE served predictions for TCS — no error, plausible confidence, entirely wrong. Now scoped by `(name, task)`, with a regression test. |
| Realized P&L discarded on sells | Any portfolio that had taken profit reported a total return that was too low. |
| Sells accepted beyond held quantity | Produced a negative position that every downstream weight calculation divided by. |
| `BaseRepository.list` shadowed the `list` builtin | The module could not be imported at all (`TypeError: 'function' object is not subscriptable`). |
| `bulk_upsert` loaded all historical timestamps | O(total history) memory per import, growing unbounded. Now bounded to the incoming batch's range. |
| N+1 latest-price queries | A 40-symbol watchlist issued 40 round-trips. One bulk query now. |
| N+1 document lookups per RAG chunk | 2,000 SELECTs per copilot question on a 2,000-chunk corpus. |
| Holdings rebuilt with a commit per row | ~40 transactions per order on a 20-position portfolio, and no enclosing transaction, so a crash mid-rebuild left it half-written. |
| SQLite foreign keys never enabled | Every `ondelete="CASCADE"` was a silent no-op in dev and in tests. |
| No `pool_recycle` on PostgreSQL | Intermittent "server closed the connection unexpectedly" under low traffic. |
| Session not rolled back on exception | A failed request could return a poisoned connection to the pool and break an *unrelated* later request. |
| Rate-limiter dict grew without bound | Memory leak proportional to unique client IPs ever seen. |
| `CORS_ORIGINS=a,b` crashed at boot | pydantic-settings parses complex types as JSON first. Both forms now accepted. |
| Bare `except Exception` in the signal path | Swallowed genuine ML bugs and reported them as "no model trained". |
| Stack traces returned to clients on 500 | Leaked file paths, dependency versions and sometimes SQL. |
| Two incompatible error shapes | Domain errors and validation errors returned different JSON; the frontend special-cased both. |
| Uncapped `limit` on list endpoints | Trivial denial-of-service vector. |
| Multipart upload set `Content-Type` manually | Produced a header with no boundary; the server rejected the body. |

### Added

**Backend** — market registry (IN/US), market overview service (indices, movers,
sectors, heatmap, breadth, 52-week), news intelligence with lexicon sentiment,
watchlists, report generation (PDF/Excel/CSV × 4 report types), admin analytics,
settings persistence, Monte Carlo / correlation / stress testing, multi-day price
forecasts, prediction history scored against outcomes, copilot conversation
threading, SSE streaming, structured logging with request correlation, security
headers, and per-request audit telemetry.

Routes went from 6 to 11 routers; tests from 192 to 203.

**Frontend** — a complete rebuild: design tokens, ~15 owned UI primitives, 9 chart
components (including a real squarified treemap), 11 pages, a command palette,
market switcher, mobile bottom navigation, and consistent loading/error/empty
states everywhere.

### Changed

- Error responses carry a stable machine-readable `code`.
- `replay_orders` returns `Position` objects rather than tuples.
- A fully-closed position is retained with quantity 0 so its realized P&L stays
  reportable.
- `document_type` is an enum on the endpoint signature (422 instead of a
  hand-rolled 400).
- `next lint` → `eslint` directly (Next 16 removed the wrapper).
- ESLint uses `eslint-config-next`'s native flat configs; the FlatCompat shim
  throws against v16.

### Known limitations

Stated in the UI as well as here: synthetic price history, lexicon (not
transformer) sentiment, constant-holdings performance series, server-side-then-chunked
SSE, per-process rate limiting, and no Users/Subscriptions admin panels because
the platform has neither.
