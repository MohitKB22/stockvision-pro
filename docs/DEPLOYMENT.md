# Deployment

## Docker Compose (recommended)

```bash
cp .env.example .env
# edit .env — at minimum set POSTGRES_PASSWORD
docker compose up --build -d
docker compose exec api alembic upgrade head     # PostgreSQL needs migrations
docker compose exec api python scripts/seed_data.py
```

Services: `postgres`, `redis`, `api`, `web`, `nginx`.
Optional profiles: `--profile worker` (Celery worker + beat),
`--profile obs` (Prometheus + Grafana).

### Same-origin setup

Behind the bundled NGINX, set `NEXT_PUBLIC_API_URL=/api/v1`. The browser then
makes no cross-origin request at all and no CORS preflight is involved. Note this
value is compiled into the client bundle at **build** time, so changing it
requires rebuilding the `web` image, not just restarting it.

## Environment variables

| Variable | Default | Notes |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | `development` / `staging` / `production` / `test` |
| `DATABASE_URL` | `sqlite:///./stockvision.db` | Use `postgresql://…` in production |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | `10` / `20` | PostgreSQL only |
| `REDIS_URL` | `redis://localhost:6379/0` | |
| `CELERY_BROKER_URL` | `redis://localhost:6379/1` | |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated **or** JSON |
| `LOG_FORMAT` | `console` | Use `json` in production |
| `LOG_LEVEL` | `INFO` | |
| `RATE_LIMIT_PER_MINUTE` | `600` | Per client IP |
| `MAX_UPLOAD_BYTES` | `26214400` | 25 MB; keep NGINX's `client_max_body_size` above it |
| `DOCUMENT_STORAGE_DIR` | `./document_storage` | Must be a persistent volume |
| `MODEL_ARTIFACT_DIR` | `./ml_artifacts` | Must be a persistent volume |
| `REPORT_STORAGE_DIR` | `./report_storage` | Must be a persistent volume |
| `OPENAI_API_KEY` / `GEMINI_API_KEY` | unset | Without either, the copilot uses the extractive fallback |
| `ALPHA_VANTAGE_API_KEY` / `POLYGON_API_KEY` | unset | Enables the live price refresh task |

`CORS_ORIGINS` accepts a plain comma-separated string. pydantic-settings parses
complex types as JSON first, so the natural `a.com,b.com` form used to crash the
process at boot — that is fixed, but the JSON form still works too.

## Migrations

```bash
alembic upgrade head              # apply
alembic revision --autogenerate -m "description"
alembic downgrade -1              # roll back one
```

SQLite deployments auto-create tables at startup for convenience. **PostgreSQL
does not** — `create_all()` only creates missing tables and cannot apply schema
*changes*, which is exactly the gap versioned migrations cover. Auto-creating in
production would silently mask a forgotten migration.

## Health checks

| Endpoint | Purpose |
| --- | --- |
| `/health` | Liveness — is the process alive |
| `/health/ready` | Readiness — can it serve traffic (probes the DB) |
| `/metrics` | Prometheus (restricted to private ranges in the NGINX config) |

Point your orchestrator's liveness probe at `/health` and its readiness probe at
`/health/ready`. Conflating the two means traffic keeps routing to a replica whose
database connection is broken.

## Scaling notes

**Rate limiting is per-process.** The in-memory sliding window does not coordinate
across replicas, so N replicas allow roughly N× the configured rate. For
multi-replica deployments, replace the body of `rate_limiter` in
`app/core/dependencies.py` with a Redis token bucket — the interface (a callable
FastAPI dependency) is unchanged, so no call site moves.

**Model training is synchronous.** Fine at seeded scale (seconds). For production
datasets, move it behind the Celery task in `app/worker.py` and add a job-status
endpoint.

**Storage volumes matter.** Losing `ml_artifacts` on redeploy silently degrades
every prediction back to indicators-only, because the registry rows survive but
their artifacts do not.

## Security checklist

- [ ] Set a real `POSTGRES_PASSWORD`
- [ ] Terminate TLS at the proxy or load balancer
- [ ] Keep the API on a private network — **it is unauthenticated by design**
- [ ] Restrict `/metrics` to your scraper's address
- [ ] Set `LOG_FORMAT=json` so an aggregator can parse the logs
- [ ] Confirm `CORS_ORIGINS` lists only origins you control

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| Frontend loads, all data fails | `NEXT_PUBLIC_API_URL` wrong — it is baked at build time |
| `connection refused` on first boot | Missing `depends_on: service_healthy`; retry once |
| `InFailedSqlTransaction` on unrelated requests | A pooled connection returned mid-abort — fixed by the rollback in `get_db` |
| Copilot answers labelled `extractive_fallback` | No LLM key configured; this is expected, not a failure |
| Reports 404 on download | `REPORT_STORAGE_DIR` is not a persistent volume |
