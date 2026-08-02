#!/usr/bin/env bash
#
# Starts the API, handling the three things that actually go wrong locally:
#
#   1. a crashed `--reload` worker still holding port 8000, which makes the
#      browser TIME OUT rather than refuse the connection
#   2. the virtualenv not being active, so uvicorn runs under the wrong Python
#   3. an unseeded database
#
# Usage:  ./start-backend.sh [port]
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/stockvision-backend"
PORT="${1:-8000}"

cd "$BACKEND"

# --- virtualenv ------------------------------------------------------------
if [ ! -d .venv ]; then
  echo "No .venv found. Creating one with python3.12..."
  if ! command -v python3.12 >/dev/null 2>&1; then
    echo "python3.12 is not installed. Run: brew install python@3.12"
    exit 1
  fi
  python3.12 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python -m pip install --upgrade pip
  pip install -r requirements.txt
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "Python:  $(python -c 'import sys; print(sys.executable)')"

# --- free the port ---------------------------------------------------------
if lsof -ti:"$PORT" >/dev/null 2>&1; then
  echo "Port $PORT is in use by PID(s): $(lsof -ti:"$PORT" | tr '\n' ' ')"
  echo "Killing it — this is almost always a crashed uvicorn reloader from an earlier run."
  lsof -ti:"$PORT" | xargs kill -9 2>/dev/null || true
  sleep 1
fi

# --- database --------------------------------------------------------------
if [ ! -f stockvision.db ]; then
  echo "No database found — seeding both markets (this takes ~20s)..."
  python scripts/seed_data.py
fi

# --- point the frontend at this port ---------------------------------------
ENV_LOCAL="$ROOT/stockvision-frontend/.env.local"
{
  echo "# Written by start-backend.sh. Delete this file to fall back to demo mode."
  echo "NEXT_PUBLIC_DEMO_MODE=false"
  echo "NEXT_PUBLIC_API_URL=http://127.0.0.1:$PORT/api/v1"
} > "$ENV_LOCAL"
echo "Wrote $ENV_LOCAL"

echo
echo "Starting the API on http://127.0.0.1:$PORT"
echo "  health : http://127.0.0.1:$PORT/health"
echo "  docs   : http://127.0.0.1:$PORT/docs"
echo "  (the UI is on :3000 — this port serves JSON only)"
echo

exec python -m uvicorn app.main:app --reload --host 127.0.0.1 --port "$PORT"
