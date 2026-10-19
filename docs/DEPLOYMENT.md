# Deployment

Two supported targets: **free hosting on Vercel + Neon** (the public demo) and
**Docker Compose** (a self-hosted stack with Redis, Celery and NGINX).

## Free hosting (Vercel + Neon)

Everything stays on free tiers: Vercel **Hobby** for the frontend and the API,
Neon's **Free** plan for PostgreSQL. Neither needs a payment method. When a free
limit is reached they stop serving rather than bill: Neon suspends the database
compute until its next monthly period, and on Vercel Hobby (which has no billing
cycle at all) the over-limit feature is unavailable until 30 days have passed.
Hobby is for **non-commercial** use only. Free-tier terms can change, so re-check
[vercel.com/pricing](https://vercel.com/pricing) and
[neon.com/pricing](https://neon.com/pricing) occasionally.

| Part | Where | Notes |
| --- | --- | --- |
| Frontend | Vercel project `stockvision-pro`, Root Directory `stockvision-frontend` | `NEXT_PUBLIC_API_URL` = API URL + `/api/v1` (set at build) |
| API | Vercel project `stockvision-pro-api`, Root Directory `stockvision-backend` | One Python function (`app/main.py`), 300 s max, 2 GB |
| Database | Neon project, region AWS us-east-1 (next to Vercel's default `iad1`) | Use the **pooled** connection string |

### One-time setup

1. Neon: create a free project and copy its connection string.
2. Vercel: create an access token (Account Settings → Tokens).
3. GitHub: add both as repository secrets — `DATABASE_URL` and `VERCEL_TOKEN`.

That is all. `.github/workflows/deploy.yml` runs after CI passes on `main` (or
manually from the Actions tab). It creates both Vercel projects if they do not
exist, sets their environment variables, deploys the API and then the frontend
built against it, and smoke-tests the live site with `scripts/smoke_test.py`.
The URLs and the test result appear as annotations on the workflow run.

### Or: set it up in the Vercel dashboard (no secrets in GitHub)

1. **Add New → Project**, import this repository. Name `stockvision-pro-api`,
   Framework Preset **FastAPI**, Root Directory `stockvision-backend` (the build
   command comes from its `vercel.json`). Add the environment variables
   `ENVIRONMENT=production`, `LOG_FORMAT=json`,
   `CORS_ORIGIN_REGEX=^https://stockvision-pro(-[a-z0-9]+)*\.vercel\.app$`,
   `STORAGE_QUOTA_BYTES=314572800`, `REPORT_RETENTION_COUNT=50`,
   `RATE_LIMIT_PER_MINUTE=300`, then Deploy. The first build stops with
   "no PostgreSQL database is configured" — expected.
2. In that project: **Storage → Create Database → Neon**, plan **Free**, region
   Washington D.C. (`iad1`), connect it to Production and Preview with **no**
   variable prefix (it injects `DATABASE_URL` / `DATABASE_URL_UNPOOLED`).
   Then **Deployments → ⋯ → Redeploy**. The build migrates and seeds the database.
3. **Add New → Project** again with the same repository: name `stockvision-pro`,
   preset **Next.js**, Root Directory `stockvision-frontend`, environment variable
   `NEXT_PUBLIC_API_URL=https://<API production domain>/api/v1`, Deploy.
4. Check it: Actions → **Verify live deployment** → Run workflow with both URLs
   (37 HTTP checks plus a headless-browser pass over all 11 pages).

If Vercel gives the frontend a domain that does not start with `stockvision-pro`,
also set `CORS_ORIGINS=https://<that domain>` on the API project and redeploy it.

### What changes on serverless

Detected automatically from the `VERCEL` environment variable:

| Concern | Docker / local | Vercel |
| --- | --- | --- |
| Model artifacts, reports, uploaded PDFs | files under `*_STORAGE_DIR` | `stored_files` table (`STORAGE_BACKEND=database`) — the function's disk is read-only and per-instance |
| Schema + seed data | `alembic upgrade head` + `seed_data.py` by hand | the build step (`scripts/vercel_build.py`) — idempotent, preview builds skip it |
| Upload limit | 25 MB | 4 MB (Vercel rejects request bodies over 4.5 MB) |
| Training per request | ≤ 200 Optuna trials, ≤ 20 splits | ≤ 40 trials, ≤ 8 splits (300 s function limit) |
| DB pool per process | 10 + 20 | 5 + 15, 240 s recycle (Neon suspends idle compute) |
| `/metrics` | on | off (per-instance counters nobody scrapes) |
| Celery price refresh | `--profile worker` | not run (no provider key is configured on the demo) |

The API's dependencies are split so the function fits Vercel's 500 MB Python
limit: `requirements.txt` is runtime-only (433 MB installed), with test tools in
`requirements-dev.txt` and `chromadb` in `requirements-optional.txt`. SHAP values
come from XGBoost/LightGBM's built-in TreeSHAP (forests are translated into an
equivalent XGBoost ensemble) instead of the `shap` package, whose numba/LLVM
dependency alone is ~190 MB; `tests/test_explain.py` checks they match `shap`.

Public-demo guards (set by the deploy workflow): `STORAGE_QUOTA_BYTES=300 MB`,
`REPORT_RETENTION_COUNT=50`, `RATE_LIMIT_PER_MINUTE=300`, and client IPs are
truncated before the audit log stores them (`AUDIT_ANONYMIZE_IP`, on by default).

---

## Docker Compose (recommended for self-hosting)

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
| `DATABASE_URL` | `sqlite:///./stockvision.db` | Use `postgresql://…` in production; `postgres://` is accepted. Falls back to `POSTGRES_URL`, `DATABASE_URL_UNPOOLED`, `POSTGRES_URL_NON_POOLING` |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | `10` / `20` (`5` / `15` on serverless) | PostgreSQL only |
| `STORAGE_BACKEND` | `filesystem` (`database` on serverless) | Where artifacts, reports and PDFs are kept |
| `STORAGE_QUOTA_BYTES` / `REPORT_RETENTION_COUNT` | `0` / `0` | Caps for public deployments (0 = unlimited) |
| `CORS_ORIGIN_REGEX` | unset | Extra origins by pattern, e.g. preview deployments |
| `ML_MAX_OPTUNA_TRIALS` / `ML_MAX_WALK_FORWARD_SPLITS` | `200` / `20` (`40` / `8` on serverless) | Per-request training budget |
| `AUDIT_ANONYMIZE_IP` | `true` | Truncate client IPs before storing them |
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

`CORS_ORIGINS` accepts a plain comma-separated string or a JSON array.
pydantic-settings JSON-decodes list fields read from the environment before any
validator runs, so the comma-separated form used to crash the process at boot
when it came from a real environment variable; the field is now marked
`NoDecode` and parsed by the validator (regression-tested in
`tests/test_deployment.py`).

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
