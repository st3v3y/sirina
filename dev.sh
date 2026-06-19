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

# Wait until the backend port accepts connections, so Vite's proxy doesn't spam
# ECONNREFUSED for /api/status while uvicorn is still starting. Caps at ~60s, then
# starts the frontend anyway (its BackendGate keeps polling).
wait_for_backend() {
  printf '\033[2m[dev] waiting for backend on :%s…\033[0m\n' "$BACKEND_PORT"
  local tries=0
  until (exec 3<>"/dev/tcp/127.0.0.1/$BACKEND_PORT") 2>/dev/null; do
    tries=$((tries + 1))
    if [ "$tries" -ge 120 ]; then
      printf '\033[2m[dev] backend not up yet — starting frontend anyway.\033[0m\n'
      return 0
    fi
    sleep 0.5
  done
  exec 3>&- 2>/dev/null || true
  printf '\033[2m[dev] backend is up.\033[0m\n'
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

# Give the backend a head start so the Vite proxy has something to connect to.
wait_for_backend

# Frontend
(
  cd "$ROOT/frontend"
  exec npm run dev -- --port "$FRONTEND_PORT"
) 2>&1 | prefix "\033[35m[frontend]\033[0m" &

wait
