# Developer Guide

## Setup

```bash
# Backend
cd stockvision-backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/seed_data.py
uvicorn app.main:app --reload

# Frontend
cd stockvision-frontend
npm install
npm run dev
```

## Commands

| Command | What it does |
| --- | --- |
| `pytest -q` | 203 backend tests |
| `ruff check app scripts tests migrations` | Lint |
| `python scripts/seed_data.py --reset` | Drop and reseed both markets |
| `python scripts/e2e_api_test.py` | 89 endpoint assertions |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run lint` | ESLint |
| `npm run verify` | typecheck + lint + build |

## Conventions

**Backend**

- Endpoints parse and delegate. If a handler is longer than ~30 lines, the logic
  belongs in a service.
- Services raise domain exceptions (`NotFoundException`), never `HTTPException`.
  That is what keeps them reusable from Celery and from scripts.
- Repositories are the only place `Session` appears.
- Every new exception gets a stable `code` — the frontend branches on it.
- Bulk over N+1: if you are about to loop and query per item, add a
  `..._bulk` repository method instead.

**Frontend**

- Query keys go in `lib/query-keys.ts`. Never inline them.
- Data hooks read the market from context; do not thread it as a prop.
- Formatting goes through `lib/format.ts` so digit grouping stays market-driven.
- Every data view needs loading, error and empty states. `ErrorState` already
  renders `isEmptyState` codes as empty states rather than as errors.
- `any` is a lint error. If a third-party type genuinely cannot be narrowed, write
  a real type guard (see `isCandlestickSeries` in `price-chart.tsx`).

## Adding a feature end to end

Say you want "dividend history".

1. **Model** — `app/models/market.py`: add `Dividend`. Register it in
   `app/models/__init__.py` so `create_all` and Alembic see it.
2. **Migration** — `alembic revision --autogenerate -m "add dividends"`, then read
   the generated file. Autogenerate misses index and server-default details.
3. **Repository** — `DividendRepository` in `app/repositories/market_repository.py`.
   Add a `_bulk` variant if any view needs it for many symbols.
4. **Schema** — request/response models in `app/schemas/market.py`.
5. **Service** — the business logic. Raise domain exceptions.
6. **Endpoint** — thin handler in `app/api/v1/endpoints/stocks.py`.
7. **Test** — add to `tests/test_stocks_api.py`, including the failure path.
8. **Frontend type** — mirror the schema in `src/types/index.ts`.
9. **Query key** — add to `lib/query-keys.ts`.
10. **Hook** — in the matching `src/hooks/use-*.ts`.
11. **UI** — consume the hook; handle all three non-success states.

## Testing notes

Each test gets a fresh in-memory SQLite database via the `client` fixture, which
also disables the rate limiter (Starlette's TestClient reports one fake host for
every request, so the module-level counter would otherwise accumulate across the
whole session and 429 unrelated later tests). Rate limiting has its own test file
that deliberately does *not* override it.

Prefer tests that would have caught a real bug. The most valuable ones here are:

- `test_a_models_predictions_are_scoped_to_its_own_symbol` — the cross-symbol
  model leak
- `test_selling_more_than_held_is_rejected` — negative positions
- `test_realized_pnl_is_booked_on_a_partial_sell` — silently discarded P&L
- `test_monte_carlo_is_deterministic_for_the_same_inputs` — a risk figure that
  changes on refresh is not a risk figure
- `test_symbols_without_two_bars_are_omitted_not_faked` — no invented numbers

## Gotchas

- **`limit` is capped at 500.** Deliberate. Paginate instead.
- **Percentages are ratios.** `formatPercent(0.0521)` → "+5.21%". Passing an
  already-multiplied value is the most common bug in this codebase's ancestor.
- **Do not name a method `list` in a class that later annotates `-> list[T]`.**
  The method shadows the builtin for the rest of the class body and the module
  fails to import. `app/repositories/base.py` uses
  `from __future__ import annotations` for exactly this reason.
- **`datetime.UTC` is 3.11+.** The source targets 3.10 as a floor; use
  `timezone.utc`.
- **`NEXT_PUBLIC_*` is compiled in at build time.** Changing it needs a rebuild.
- **Chart parents need an explicit height.** Recharts' ResponsiveContainer
  measures its parent and renders at 0px if that parent has no height — which
  looks like a broken chart, not a layout bug. `ChartFrame` enforces it.
