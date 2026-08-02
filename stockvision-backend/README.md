# StockVision Pro — Backend

FastAPI service: market data, portfolio and risk analytics, ML prediction, and a
RAG copilot over financial documents.

> **This API is unauthenticated by design.** There is no login, no JWT and no
> session. Run it behind a private network boundary or a proxy that terminates
> access control. See the root [README](../README.md) and
> [docs/CHANGELOG.md](../docs/CHANGELOG.md) for why.

## Run it

Requires **Python 3.10–3.13** — not 3.14, whose missing wheels for `faiss-cpu`,
`xgboost`, `shap` and `scipy` break the install halfway.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python scripts/seed_data.py             # both markets, ~3 years of synthetic OHLCV
python -m uvicorn app.main:app --reload # http://localhost:8000/docs
```

Use `python -m uvicorn`, not bare `uvicorn` — a global uvicorn earlier in `PATH`
runs under its own interpreter and will fail with `No module named 'app'`.

Defaults to a local SQLite file, so no external services are required. Point
`DATABASE_URL` at PostgreSQL for production and run `alembic upgrade head`.

Setup problems are covered in the root [README](../README.md#troubleshooting).

## Layout

```
app/
├── api/v1/endpoints/   HTTP layer. Parses, delegates. No business logic.
├── core/               config, database, logging, middleware, exceptions
├── domain/             enums + the IN/US market registry
├── models/             SQLAlchemy ORM
├── repositories/       every database access
├── schemas/            Pydantic request/response contracts
├── services/           business logic — reusable outside HTTP
├── ml/                 indicators, training, SHAP, model registry
└── rag/                PDF extraction, chunking, embeddings, vector stores
```

Layering rule: `endpoints → services → repositories → models`. An endpoint never
touches a `Session`; a service never sees a `Request` and raises domain
exceptions rather than `HTTPException`. That is what lets one service back an
HTTP route, a Celery task and the PDF report generator.

## Commands

| Command | Purpose |
| --- | --- |
| `pytest -q` | 203 tests |
| `ruff check app scripts tests migrations` | Lint |
| `python scripts/seed_data.py --reset` | Drop and reseed |
| `python scripts/e2e_api_test.py` | 89 endpoint assertions (needs a seeded DB) |
| `python scripts/check_no_auth.py` | CI guard: assert auth has not returned |
| `python scripts/train_model.py --symbol RELIANCE` | Train from the CLI |
| `alembic upgrade head` | Apply migrations |

## Notes

- **Synthetic price history.** No market-data provider is reachable from this
  environment. The real clients exist in `app/services/market_data_providers.py`
  and are wired to the Celery refresh task; add an API key and the same tables
  fill with real bars.
- **Model training is synchronous.** Seconds on seeded data. For production
  volumes, move it behind `app/worker.py`.
- **Rate limiting is per-process.** Swap the body of `rate_limiter` in
  `app/core/dependencies.py` for a Redis token bucket to scale across replicas —
  the interface is unchanged.

Full detail: [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) ·
[docs/API.md](../docs/API.md)
