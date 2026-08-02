# Deploying to Vercel

The 404 you get from a fresh import of this repository is not a bug in the app.
It is one project setting.

## Why the 404 happens

This is a monorepo. The repository root contains `stockvision-frontend/` and
`stockvision-backend/`, and **no `package.json` of its own**. Vercel's default
Root Directory is `/`, so the build finds no application, produces an empty
deployment, and reports it as *Ready*. Every path then returns:

```
404: NOT_FOUND
```

An empty deployment is a successful build of nothing.

## The fix — one setting

1. Vercel → your project → **Settings → Build & Deployment**
2. **Root Directory** → `stockvision-frontend` → **Save**
   (Framework Preset should switch to *Next.js* on its own.)
3. **Deployments** → latest → ⋯ → **Redeploy**, with "use existing build cache"
   unchecked.

That is the whole fix. Root Directory cannot be set from `vercel.json` — it is a
project setting only, which is why this file cannot do it for you.

> Importing the repository fresh? Set Root Directory to `stockvision-frontend`
> on the import screen and you will never see the 404 at all.

## What you get after the redeploy

The deployment runs in **demo mode**, which is turned on by
`stockvision-frontend/.env.production` (committed on purpose). The frontend
answers its own API calls from a generated dataset in the browser, so the
deployed site is fully usable with no backend: dashboard, market pages, heatmap,
portfolio, risk engine, ML forecasts, signals, copilot, reports and admin all
work. See [DEMO_MODE.md](DEMO_MODE.md) for what is real and what is generated.

The UI shows a **"Demo data"** badge in the top bar the whole time it is on.

## Connecting a real backend later

The FastAPI service cannot run on Vercel — it needs a writable filesystem, a
database, FAISS and Celery. Deploy it to Render, Railway, Fly.io or any Docker
host (`stockvision-backend/Dockerfile` is ready), then in the Vercel project:

| Environment variable    | Value                                  |
| ----------------------- | -------------------------------------- |
| `NEXT_PUBLIC_DEMO_MODE` | `false`                                |
| `NEXT_PUBLIC_API_URL`   | `https://your-backend.example/api/v1`  |

Both are read at **build** time, so redeploy after setting them. Dashboard values
override `.env.production`.

Set the backend's `CORS_ORIGINS` to your Vercel URL, or the browser will block
the requests.

### One thing to think about first

`README.md` states plainly that this API is unauthenticated by design. Putting it
on the public internet means anyone who finds the URL can trigger model training,
upload PDFs and generate reports on your instance. For a portfolio link, demo
mode is both the cheaper and the safer option; if you do host the backend, put it
behind the bundled NGINX (`deploy/nginx/`) with an allowlist, or keep it private
and share the demo.

## Repository hygiene

If your GitHub repository was created by drag-and-drop upload, check for
artifacts at the root that do not belong there — a stray `package-lock.json`, or
duplicated `app/`, `ml/`, `schemas/`, `services/` folders that also exist inside
`stockvision-backend/`. They do not break the build once Root Directory is set,
but they confuse anyone reading the repo. The layout in this archive is the
correct one.
