#!/usr/bin/env bash
#
# Starts the UI on http://localhost:3000.
#
# Pass --demo to run with no backend at all: the frontend answers its own API
# calls from generated data (see DEMO_MODE.md) and shows a "Demo data" badge.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT/stockvision-frontend"

if [ "${1:-}" = "--demo" ]; then
  {
    echo "# Written by start-frontend.sh --demo. Delete this file to use a real backend."
    echo "NEXT_PUBLIC_DEMO_MODE=true"
  } > .env.local
  echo "Demo mode ON — no backend required."
fi

[ -d node_modules ] || npm install

exec npm run dev
