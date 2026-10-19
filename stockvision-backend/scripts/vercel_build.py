#!/usr/bin/env python3
"""
Build step for the Vercel deployment of the API (the project's Build Command).

Vercel runs this after installing requirements.txt and before packaging the
FastAPI function. It prepares the database, so no request ever has to:

  1. refuse to continue without PostgreSQL — a serverless filesystem is read-only
     and per-instance, so SQLite cannot hold this app's data there
  2. `alembic upgrade head`
  3. seed the reference dataset (scripts/seed_data.py — idempotent: stocks are
     upserted, existing bars are skipped, portfolios/watchlists/news are only
     created once)

Uses the direct (non-pooled) connection string when the provider supplies one,
because schema changes through a transaction-mode pooler are unreliable.

Preview deployments skip all database writes unless ALLOW_PREVIEW_DB_WRITES=1:
by default a preview shares the production database, and a migration from an
unmerged branch must never run against it.

Any failure fails the build, so a broken release never replaces the live one.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
DIRECT_URL_VARS = ("DATABASE_URL_UNPOOLED", "POSTGRES_URL_NON_POOLING")


def log(message: str) -> None:
    print(f"[build] {message}", flush=True)


def run(*args: str, env: dict[str, str]) -> None:
    started = time.perf_counter()
    log("$ " + " ".join(args))
    result = subprocess.run(args, cwd=BACKEND, env=env)
    if result.returncode != 0:
        raise SystemExit(f"[build] FAILED ({result.returncode}): {' '.join(args)}")
    log(f"  done in {time.perf_counter() - started:.1f}s")


def main() -> int:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(BACKEND), env.get("PYTHONPATH")]))
    for name in DIRECT_URL_VARS:
        if env.get(name, "").strip():
            env["DATABASE_URL"] = env[name].strip()
            log(f"using {name} (direct connection) for migrations and seeding")
            break

    sys.path.insert(0, str(BACKEND))
    if env.get("DATABASE_URL"):
        os.environ["DATABASE_URL"] = env["DATABASE_URL"]
    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    if settings.is_sqlite:
        log("FAILED: no PostgreSQL database is configured.")
        log("  Set DATABASE_URL (or connect a Postgres integration such as Neon's free plan,")
        log("  which injects it) in the project's environment variables, then redeploy.")
        return 1

    if env.get("VERCEL_ENV") == "preview" and env.get("ALLOW_PREVIEW_DB_WRITES", "").lower() not in ("1", "true"):
        log("preview deployment: skipping migrations and seeding (set ALLOW_PREVIEW_DB_WRITES=1 "
            "if previews use their own database branch)")
        return 0

    run(sys.executable, "-m", "alembic", "upgrade", "head", env=env)
    run(sys.executable, "scripts/seed_data.py", env=env)
    log("database ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
