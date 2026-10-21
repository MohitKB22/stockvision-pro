#!/usr/bin/env python3
"""
Deploys StockVision Pro to Vercel (free Hobby plan) as two projects:

  stockvision-pro-api  FastAPI backend   (Root Directory: stockvision-backend)
  stockvision-pro-web  Next.js frontend  (Root Directory: stockvision-frontend)

and then smoke-tests the live result. Run by .github/workflows/deploy.yml; needs

  VERCEL_TOKEN   a Vercel access token for the account to deploy to
  DATABASE_URL   PostgreSQL connection string (Neon free plan)

Steps: resolve the account -> create each project if missing (settings are
corrected if it exists) -> upsert its environment variables -> `vercel deploy
--prod` from the repository root -> read the project's production *.vercel.app
domain -> run stockvision-backend/scripts/smoke_test.py against the live URLs.

Standard library only. Secrets are only ever sent to api.vercel.com and are
never printed. Results are reported as GitHub annotations and in the job summary.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = os.environ.get("VERCEL_API_BASE", "https://api.vercel.com")  # overridable for tests
REPO_ROOT = Path(__file__).resolve().parents[2]

API_PROJECT = os.environ.get("API_PROJECT", "stockvision-pro-api")
WEB_PROJECT = os.environ.get("WEB_PROJECT", "stockvision-pro-web")
# Frontend production + preview domains (stockvision-pro.vercel.app,
# stockvision-pro-<suffix>.vercel.app, stockvision-pro-git-main-<team>.vercel.app).
WEB_ORIGIN_REGEX = r"^https://stockvision-pro(-[a-z0-9]+)*\.vercel\.app$"

TOKEN = os.environ.get("VERCEL_TOKEN", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")


# --- GitHub reporting -------------------------------------------------------------
def notice(title: str, message: str) -> None:
    print(f"::notice title={title}::{message}", flush=True)


def error(title: str, message: str) -> None:
    print(f"::error title={title}::{message.replace(chr(10), '%0A')}", flush=True)


def summary(markdown: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(markdown + "\n")


# --- Vercel REST ------------------------------------------------------------------
class VercelError(RuntimeError):
    pass


SCOPE: dict[str, str] = {}


def call(method: str, path: str, body=None, query: dict | None = None) -> tuple[int, dict]:
    params = {**SCOPE, **(query or {})}
    url = f"{API}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {TOKEN}")
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, {"error": {"message": raw[:300].decode(errors="replace")}}
    except (urllib.error.URLError, TimeoutError) as exc:
        raise VercelError(f"Could not reach the Vercel API ({method} {path}): {exc}") from exc


def must(status: int, payload: dict, what: str) -> dict:
    if status >= 300:
        message = (payload.get("error") or {}).get("message") or json.dumps(payload)[:300]
        raise VercelError(f"{what} failed (HTTP {status}): {message}")
    return payload


def resolve_scope() -> str:
    """Returns the owner id for VERCEL_ORG_ID; sets teamId for later calls when
    the account's resources live under a (Hobby) team."""
    user = must(*call("GET", "/v2/user"), "Reading the Vercel account")["user"]
    owner = user.get("defaultTeamId") or user["id"]
    if user.get("defaultTeamId"):
        SCOPE["teamId"] = user["defaultTeamId"]
    print(f"Vercel account: {user.get('username')} (owner {owner})")
    return owner


def ensure_project(name: str, framework: str, root_directory: str) -> dict:
    status, project = call("GET", f"/v9/projects/{name}")
    wanted = {"framework": framework, "rootDirectory": root_directory}
    if status == 404:
        project = must(*call("POST", "/v11/projects", {"name": name, **wanted}), f"Creating project {name}")
        print(f"Created project {name}")
        return project
    must(status, project, f"Reading project {name}")
    if any(project.get(k) != v for k, v in wanted.items()):
        project = must(*call("PATCH", f"/v9/projects/{project['id']}", wanted), f"Updating project {name}")
        print(f"Updated project {name} settings: {wanted}")
    return project


def set_env(project_id: str, variables: dict[str, str], targets=("production", "preview")) -> None:
    body = [
        {"key": key, "value": value, "type": "encrypted", "target": list(targets)}
        for key, value in variables.items()
    ]
    result = must(*call("POST", f"/v10/projects/{project_id}/env", body, {"upsert": "true"}),
                  "Setting environment variables")
    failed = result.get("failed") or []
    if failed:
        raise VercelError("Environment variables rejected: " + "; ".join(
            f"{f['error'].get('key', '?')}: {f['error'].get('message')}" for f in failed))
    print(f"Environment variables set: {', '.join(sorted(variables))}")


def production_domain(project_id: str) -> str:
    """The project's public *.vercel.app production domain."""
    for _ in range(12):
        payload = must(*call("GET", f"/v9/projects/{project_id}/domains"), "Reading project domains")
        names = [d["name"] for d in payload.get("domains", [])
                 if d["name"].endswith(".vercel.app") and "-git-" not in d["name"]]
        if names:
            return "https://" + sorted(names, key=len)[0]
        time.sleep(5)
    raise VercelError("The project has no production .vercel.app domain yet.")


# --- deploy -----------------------------------------------------------------------------
def deploy(project: dict, owner: str, label: str) -> str:
    env = {**os.environ, "VERCEL_ORG_ID": owner, "VERCEL_PROJECT_ID": project["id"]}
    print(f"Deploying {label} ...", flush=True)
    started = time.time()
    result = subprocess.run(
        ["vercel", "deploy", "--prod", "--yes", "--token", TOKEN],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=2400,
    )
    print(result.stderr[-4000:].replace(TOKEN, "***"))
    url = (result.stdout.strip().splitlines() or [""])[-1].strip()
    if result.returncode != 0 or not url.startswith("https://"):
        logs = ""
        if url.startswith("https://"):
            inspect = subprocess.run(["vercel", "inspect", url, "--logs", "--token", TOKEN],
                                     cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=300)
            logs = (inspect.stdout + inspect.stderr)[-3500:]
        raise VercelError(f"{label} deployment failed.\n{logs or result.stderr[-3500:]}".replace(TOKEN, "***"))
    print(f"{label} deployed in {time.time() - started:.0f}s: {url}")
    return url


def wait_until_serving(url: str, path: str, attempts: int = 30) -> None:
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url + path, timeout=60) as response:
                if response.status == 200:
                    return
        except Exception:
            pass
        time.sleep(6)
    raise VercelError(f"{url}{path} did not start serving.")


def main() -> int:
    if not TOKEN or not DATABASE_URL:
        error("Deploy skipped", "Add the VERCEL_TOKEN and DATABASE_URL repository secrets.")
        return 1
    try:
        owner = resolve_scope()

        api_project = ensure_project(API_PROJECT, "fastapi", "stockvision-backend")
        set_env(api_project["id"], {
            "DATABASE_URL": DATABASE_URL,
            "ENVIRONMENT": "production",
            "LOG_FORMAT": "json",
            "CORS_ORIGIN_REGEX": WEB_ORIGIN_REGEX,
            # Free-tier guards for a public, unauthenticated demo:
            "STORAGE_QUOTA_BYTES": str(300 * 1024 * 1024),
            "REPORT_RETENTION_COUNT": "50",
            "RATE_LIMIT_PER_MINUTE": "300",
        })
        deploy(api_project, owner, "API")
        api_url = production_domain(api_project["id"])
        wait_until_serving(api_url, "/health/ready")
        notice("API", api_url)

        web_project = ensure_project(WEB_PROJECT, "nextjs", "stockvision-frontend")
        set_env(web_project["id"], {"NEXT_PUBLIC_API_URL": f"{api_url}/api/v1"})
        deploy(web_project, owner, "Frontend")
        web_url = production_domain(web_project["id"])
        wait_until_serving(web_url, "/")

        if not re.match(WEB_ORIGIN_REGEX, web_url):
            # The frontend got a domain outside the default pattern: allow it explicitly.
            set_env(api_project["id"], {"CORS_ORIGINS": web_url})
            deploy(api_project, owner, "API (CORS update)")
            wait_until_serving(api_url, "/health/ready")
        notice("Live app", web_url)
    except VercelError as exc:
        error("Deployment failed", str(exc))
        return 1

    smoke = subprocess.run(
        [sys.executable, "stockvision-backend/scripts/smoke_test.py", api_url,
         "--origin", web_url, "--frontend", web_url],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=1500,
    )
    print(smoke.stdout[-6000:], smoke.stderr[-2000:])
    last = (smoke.stdout.strip().splitlines() or ["(no output)"])
    result_line = next((line for line in reversed(last) if " passed, " in line), last[-1])
    summary(f"## Deployed\n\n- App: {web_url}\n- API: {api_url} ([docs]({api_url}/docs))\n\n"
            f"### Live smoke test\n\n```\n{smoke.stdout[-6000:]}\n```")
    if smoke.returncode != 0:
        failures = [line.strip() for line in last if line.strip().startswith("- ")][:8]
        error("Live smoke test failed", result_line + "\n" + "\n".join(failures))
        return 1
    notice("Live smoke test", result_line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
