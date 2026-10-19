#!/usr/bin/env bash
#
# Starts the UI on http://localhost:3000.
#
# The UI needs the API: start it first with ./start-backend.sh, which also writes
# stockvision-frontend/.env.local pointing the UI at the port the API bound.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT/stockvision-frontend"

[ -d node_modules ] || npm install

exec npm run dev
