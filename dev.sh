#!/usr/bin/env bash
# Start the backend (uvicorn) and the frontend (vite) together.
# Ctrl-C stops both.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5283}"

prefix() {
  # Prefix each line of stdin. awk's fflush keeps output live on both macOS and Linux.
  awk -v p="$1" '{ printf "%s %s\n", p, $0; fflush() }'
}

cleanup() {
  trap - INT TERM EXIT
  echo
  echo "stopping…"
  # Kill the whole process group so uvicorn's reload worker + vite both die.
  kill 0 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# Backend
(
  cd "$ROOT/backend"
  exec uv run uvicorn app.main:app --reload --reload-include='*.env' --port "$BACKEND_PORT"
) 2>&1 | prefix "\033[36m[backend]\033[0m" &

# Frontend
(
  cd "$ROOT/frontend"
  exec npm run dev -- --port "$FRONTEND_PORT"
) 2>&1 | prefix "\033[35m[frontend]\033[0m" &

wait
