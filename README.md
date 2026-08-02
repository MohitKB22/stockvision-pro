# StockVision Pro

AI-powered stock market analytics — market intelligence, portfolio and risk
analytics, ML price prediction, and a RAG copilot over financial documents.

Dual-market (India / United States), dark-theme only, **no authentication**.
The application opens directly on the dashboard.

---

## Deploying the frontend

The Next.js app deploys to Vercel; the FastAPI backend does not (it needs a
writable filesystem, a database, FAISS and Celery). Two files cover this:

- **[DEPLOY_VERCEL.md](DEPLOY_VERCEL.md)** — the one project setting a fresh
  import needs. Vercel's default Root Directory is the repository root, which
  holds no `package.json`, so the build deploys nothing and every path returns
  `404: NOT_FOUND`. Set **Root Directory** to `stockvision-frontend` and redeploy.
- **[DEMO_MODE.md](DEMO_MODE.md)** — production builds run with
  `NEXT_PUBLIC_DEMO_MODE=true`, so the deployed site is fully usable without a
  backend. The frontend answers its own API calls from a generated dataset and
  labels itself with a "Demo data" badge while it does. The price history is
  synthetic; the risk, indicator and Monte Carlo maths computed on it is real.

Local development is unaffected — `npm run dev` still talks to `localhost:8000`.

---

## Before you start

Three things cause almost every setup failure. Two minutes here saves an hour.

| Requirement | Why it matters |
| --- | --- |
| **Python 3.10 – 3.13** | **Not 3.14.** Several dependencies (`faiss-cpu`, `xgboost`, `shap`, `scipy`) have no 3.14 wheels yet, so `pip install` half-succeeds and the app dies on its first import. Check with `python3 --version`. |
| **Node 20+** | Next.js 16 requires it. Check with `node --version`. |
| **Two terminals** | The backend (`:8000`) and the frontend (`:3000`) are separate processes. The UI is on **3000** — `:8000` serves the API only. |

If `python3 --version` says 3.14, install a supported one:

```bash
brew install python@3.12      # macOS
```

Then use `python3.12` wherever the steps below say `python3`.

---

## Quick start — two scripts

```bash
./start-backend.sh      # terminal 1
./start-frontend.sh     # terminal 2
```

`start-backend.sh` creates the virtualenv if it is missing, installs
requirements, seeds the database on first run, **frees port 8000 if a crashed
`--reload` worker is still holding it**, points the frontend at the port it
actually bound, and starts uvicorn. Pass a port to use a different one:
`./start-backend.sh 8001`.

No backend at all? `./start-frontend.sh --demo` runs the UI against generated
data — see [DEMO_MODE.md](DEMO_MODE.md).

If something is still wrong:

```bash
cd stockvision-backend && python3 scripts/doctor.py
```

It checks the interpreter, the virtualenv, the installed packages, the seeded
tables, what is holding port 8000, your proxy settings, and whether `app.main`
imports — then prints what to do about anything it finds. It uses only the
standard library, so it runs even when the environment is broken.

---

## Quick start — local
./start-backend.sh
./start-frontend.sh

**Terminal 1 — backend**

```bash
cd stockvision-pro/stockvision-backend     # note: ONE stockvision-pro, not two
python3 -m venv .venv
source .venv/bin/activate                  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python scripts/seed_data.py                # both markets, ~3 years of history
python -m uvicorn app.main:app --reload    # use `python -m`, not bare `uvicorn`
```

Wait for `Application startup complete`.

**Terminal 2 — frontend**

```bash
cd ~/Desktop/stockvision-pro/stockvision-frontend
npm install
npm run dev
```

**Open → http://localhost:3000**

Two details that trip people up, both explained in *Troubleshooting* below: the
`cd` path has only **one** `stockvision-pro` if your shell is already inside the
extracted folder, and `python -m uvicorn` matters because bare `uvicorn` can
resolve to a different Python than your venv's.

### Quick start — Docker

Sidesteps every local Python and Node issue:

```bash
cd stockvision-pro
cp .env.example .env
docker compose up --build
docker compose exec api python scripts/seed_data.py
```

Then open **http://localhost**.

> Reviewed but not executed in the environment this was built in — if it errors,
> the local path above is the verified one.

### Where things live

| Service | URL |
| --- | --- |
| **Application UI** | http://localhost:3000 (Docker: http://localhost) |
| API root | http://localhost:8000 — returns JSON, not a page |
| API docs (Swagger) | http://localhost:8000/docs |
| Health probe | http://localhost:8000/health |

---

## Troubleshooting

### `cd: no such file or directory: stockvision-pro/stockvision-backend`

Your shell is already inside `stockvision-pro`, so the path doubled. Check with
`pwd` — if it ends in `/stockvision-pro`, just run `cd stockvision-backend`.

This one cascades: every later command then runs from the wrong directory, so
`pip` reports "Could not open requirements file", `seed_data.py` is "not found",
and uvicorn fails with `ModuleNotFoundError: No module named 'app'`. All four
symptoms, one cause.

### `ModuleNotFoundError: No module named 'app'`

Three possible causes, in order of likelihood:

1. **Wrong directory.** You must be in `stockvision-backend/` (the folder
   containing `app/`). Confirm with `ls app/main.py`.
2. **Venv not active.** Your prompt should start with `(.venv)`. If not:
   `source .venv/bin/activate`.
3. **Bare `uvicorn` resolved to a different Python.** If a global uvicorn is
   earlier in your `PATH`, it runs under its own interpreter, which has no idea
   about your venv. Always use `python -m uvicorn app.main:app --reload`.

### The browser times out on `127.0.0.1:8000` (`ERR_CONNECTION_TIMED_OUT`)

A *timeout* rather than `ERR_CONNECTION_REFUSED` means something accepted the TCP
connection and never answered. Two causes:

1. **A crashed `--reload` worker.** The reloader keeps the socket bound while its
   worker dies and restarts, so the port looks occupied but nothing serves it.
   This is what `./start-backend.sh` clears automatically; by hand it is
   `lsof -ti:8000 | xargs kill -9`.
2. **A proxy or VPN that is not bypassing localhost.** Confirm with
   `curl --noproxy '*' --max-time 5 http://127.0.0.1:8000/health` — if that
   returns JSON while the browser still hangs, it is the proxy. Add
   `127.0.0.1, localhost` to System Settings → Network → Details → Proxies.

`python3 scripts/doctor.py` distinguishes the two for you.

### `ERROR: [Errno 48] Address already in use`

A previous run still holds port 8000 — commonly a `--reload` process that was
crash-looping.

```bash
lsof -ti:8000 | xargs kill -9     # macOS/Linux
python -m uvicorn app.main:app --reload
```

Or just use a different port: `--port 8001` (then set
`NEXT_PUBLIC_API_URL=http://localhost:8001/api/v1` for the frontend).

### Browser says `ERR_CONNECTION_TIMED_OUT` on localhost

Counter-intuitive but common: a `--reload` uvicorn whose worker keeps crashing
still **binds** the port. The socket accepts your connection and then nobody
answers, which surfaces as a *timeout* rather than the `ERR_CONNECTION_REFUSED`
an genuinely empty port would give you. Check the backend terminal for a
traceback — the browser error is a symptom, not the cause.

If the backend terminal looks healthy, test it directly to rule out the browser:

```bash
curl --noproxy '*' --max-time 5 http://127.0.0.1:8000/health
```

Getting `{"status":"ok",...}` here means the API is fine and the problem is
browser-side — usually a proxy or VPN that isn't bypassing localhost. Add
`127.0.0.1, localhost` to the bypass list in
System Settings → Network → Details → Proxies.

### `pip install` fails on faiss-cpu / xgboost / shap / scipy

You're on Python 3.14 (or 3.9). Those packages have no matching wheel and the
from-source build needs compilers you probably don't have. Rebuild on 3.12:

```bash
rm -rf .venv
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### `/docs` is blank but the API works

Swagger UI loads its JavaScript from a public CDN, so `/docs` renders empty if
you're offline or the CDN is blocked — even though the backend is healthy. These
are served locally and always work:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/openapi.json
```

### The UI loads but every card says "Cannot reach the API"

That message is deliberate, not a crash — the sidebar's status dot will also be
red. It means the frontend is fine and the backend isn't reachable. Confirm the
backend terminal shows `Application startup complete`, then check
`stockvision-frontend/.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

`NEXT_PUBLIC_*` is compiled in at **build** time, so restart `npm run dev` after
changing it.

### Reset everything

```bash
cd stockvision-backend
rm -f stockvision.db
python scripts/seed_data.py --reset
```

---

## What this is

| Area | What it does |
| --- | --- |
| **Market intelligence** | Indices, gainers/losers/most-active, cap-weighted sector performance, treemap heatmap, advance-decline breadth, 52-week extremes — all computed from stored OHLCV, none hardcoded |
| **Portfolio analytics** | Holdings projected by replaying an append-only order ledger, realized + unrealized P&L, sector and asset allocation, performance series, transaction history |
| **Risk engine** | VaR by three independent methods, Expected Shortfall, Sharpe, Sortino, max drawdown, beta/alpha, Monte Carlo fan chart, correlation matrix, historical stress scenarios |
| **ML prediction** | XGBoost / LightGBM / Random Forest with walk-forward CV, Optuna hyperparameter search and SHAP attributions; DB-backed model registry with staging → production promotion |
| **AI signals** | Blends classical TA (RSI, MACD, SuperTrend, ADX, Bollinger) with the model's probability into one BUY/SELL/HOLD call, and degrades to indicators-only when no model exists |
| **AI Copilot** | PDF → extraction → chunking → embedding → FAISS/ChromaDB retrieval → LLM answer with page-level citations; multi-turn conversations |
| **News intelligence** | Finance-tuned lexicon sentiment with negation and intensifier handling |
| **Reports** | Portfolio / Risk / Prediction / Tax reports as real PDF, Excel and CSV artifacts |
| **Admin** | API volume, latency, error rate, storage consumption and the audit trail — aggregated from telemetry this app actually writes |

### First things to try

1. **Dashboard** → click **Refresh** on *Top AI Signals* to generate live BUY/SELL calls
2. **Prediction** → *Train a Model* tab → **Train on RELIANCE** (takes ~10s), then **Predict**
3. **Risk** → Monte Carlo fan chart, correlation matrix, stress scenarios
4. **Market** → *Heatmap* tab — tile area is market cap, colour is session return
5. **Reports** → generate a Portfolio PDF; it downloads immediately
6. **Copilot** → upload any PDF, then ask about it (works without an API key —
   falls back to a clearly-labelled extractive mode)
7. Switch the market **IN ⇄ US** in the top bar; currency and digit grouping
   follow (₹12,45,000 vs $1,245,000)

---

## Honest scoping

Things that are deliberately *not* what they might appear to be. Each is stated
in the UI as well as here.

- **Price history is synthetic.** No market-data provider is reachable from the
  build environment, so `scripts/seed_data.py` generates geometric-Brownian-motion
  OHLCV with regime-switching volatility. The real provider clients exist
  (`app/services/market_data_providers.py`) and are wired to the Celery refresh
  task; supply an API key and the same tables fill with real bars.
- **News sentiment is a lexicon model, not a transformer.** Deterministic, fast
  and fully inspectable. `score_sentiment` is the single seam to swap for FinBERT.
  The API always names the engine that produced a score.
- **Portfolio performance is a constant-holdings series** — current positions
  valued against historical closes, not a time-weighted return. The field is named
  for what it is.
- **The copilot streaming endpoint** completes generation server-side and then
  emits the answer in word groups over SSE. The transport is the real contract;
  swapping in a token-streaming LLM client changes only the generator body.
- **No Users or Subscriptions in the admin panel.** This platform has no accounts
  and no billing, so those tiles would be invented numbers.
- **Redis is reported as "configured", never "connected".** The API process holds
  no open Redis connection, so it does not claim a check it did not perform.

---

## Architecture

```
stockvision-pro/
├── stockvision-backend/       FastAPI · SQLAlchemy · Pydantic · scikit-learn
│   ├── app/
│   │   ├── api/v1/endpoints/  HTTP layer — thin, no business logic
│   │   ├── core/              config, DB, logging, middleware, exceptions
│   │   ├── domain/            enums + the market registry (IN/US)
│   │   ├── models/            SQLAlchemy ORM
│   │   ├── repositories/      all persistence access
│   │   ├── schemas/           Pydantic request/response contracts
│   │   ├── services/          business logic
│   │   ├── ml/                indicators, training, SHAP, registry
│   │   └── rag/               PDF, chunking, embeddings, vector stores
│   ├── migrations/            Alembic
│   ├── scripts/               seed, train, e2e, CI guards
│   └── tests/                 203 tests
├── stockvision-frontend/      Next.js 16 App Router · React 19 · TypeScript
│   └── src/
│       ├── app/(app)/         11 pages behind a shared shell
│       ├── components/        ui primitives, charts, layout, feature widgets
│       ├── hooks/             React Query data layer
│       ├── lib/               api client, formatting, query keys, tokens
│       └── types/             the API contract, mirrored
├── deploy/nginx/              reverse proxy: one origin for SPA + API
└── docs/                      architecture, API, deployment, developer guide
```

Layering rule: `endpoints → services → repositories → models`. An endpoint never
touches a Session; a service never sees a Request. That is what lets the same
service back an HTTP route, a Celery task and the report generator.

Full detail in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Verification

```bash
# Backend — 203 tests, ruff clean
cd stockvision-backend
pytest -q
ruff check app scripts tests migrations
python scripts/check_no_auth.py

# End-to-end — 89 endpoint assertions against a seeded DB
python scripts/seed_data.py --market IN
python scripts/e2e_api_test.py

# Frontend — zero TS errors, zero lint issues, clean build
cd ../stockvision-frontend
npm run verify        # typecheck + lint + no-auth guard + build
```

CI runs all of the above plus both Docker image builds on every push.

---

## Documentation

| Document | Contents |
| --- | --- |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layering, data flow, design decisions and their trade-offs |
| [API.md](docs/API.md) | Every endpoint, the error envelope, response shapes |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Docker, environment variables, migrations, scaling notes |
| [DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) | Local setup, conventions, how to add a feature |
| [CHANGELOG.md](docs/CHANGELOG.md) | What changed from v1 to v2 and why |

---

## Security posture

**This API is unauthenticated by design.** Run it behind a private network
boundary or a reverse proxy that terminates access control. Do not expose it
directly to the public internet.

What is in place: security response headers, a per-IP rate limiter (edge + app),
strict upload size limits, hard pagination caps, no stack traces in error
responses, and API keys that are never readable through HTTP.
