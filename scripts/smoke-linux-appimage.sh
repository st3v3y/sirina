#!/usr/bin/env bash
# Smoke-test a Sirina AppImage (CI runs this after build-linux.sh):
#   1. unpack it and check the backend is byte-identical to the build's copy (linuxdeploy
#      and the repack left its libraries alone);
#   2. run the unpacked resources/backend/backend and wait for /api/status;
#   3. launch the AppImage itself under Xvfb and wait until the shell has started the
#      backend from the AppImage's mount and it answers /api/status.
#
# Usage: smoke-linux-appimage.sh <Sirina.AppImage> [<backend onedir it should contain>]
# Step 3 needs xvfb-run and FUSE; SKIP_LAUNCH=1 skips it.
set -euo pipefail

[ $# -ge 1 ] || { echo "usage: $0 <Sirina.AppImage> [<backend onedir>]" >&2; exit 2; }
APPIMAGE="$(realpath "$1")"
EXPECTED="${2:+$(realpath "$2")}"
PORT="${PORT:-8765}"
TIMEOUT="${TIMEOUT:-120}"  # seconds for the backend to answer

WORK="$(mktemp -d)"
PIDS=()
cleanup() {
  for pid in "${PIDS[@]}"; do kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true; done
  rm -rf "$WORK"
}
trap cleanup EXIT

# wait_status <port> <pid to watch> <log>: poll /api/status until it answers or <pid> dies.
wait_status() {
  local port=$1 pid=$2 log=$3
  for _ in $(seq "$TIMEOUT"); do
    if curl -fsS "http://127.0.0.1:$port/api/status" -o "$WORK/status.json" 2>/dev/null; then
      echo "    /api/status: $(head -c 300 "$WORK/status.json")"
      return 0
    fi
    kill -0 "$pid" 2>/dev/null || { echo "  ✗ exited before answering; log:" >&2; tail -50 "$log" >&2; return 1; }
    sleep 1
  done
  echo "  ✗ no answer from /api/status after ${TIMEOUT}s; log:" >&2
  tail -50 "$log" >&2
  return 1
}

echo "==> Unpacking $(basename "$APPIMAGE")"
(cd "$WORK" && "$APPIMAGE" --appimage-extract >/dev/null)
BACKEND="$(find "$WORK/squashfs-root/usr/lib" -path '*/resources/backend/backend' -type f -print -quit)"
[ -n "$BACKEND" ] || { echo "  ✗ no resources/backend/backend in the AppImage" >&2; exit 1; }
echo "    ${BACKEND#"$WORK/squashfs-root/"}"

if [ -n "$EXPECTED" ]; then
  echo "==> Comparing the bundled backend with $EXPECTED"
  diff -r "$EXPECTED" "$(dirname "$BACKEND")" >/dev/null || {
    echo "  ✗ the AppImage's backend differs from the build's:" >&2
    diff -rq "$EXPECTED" "$(dirname "$BACKEND")" | head -20 >&2
    exit 1
  }
  echo "    identical"
fi

echo "==> Starting the unpacked backend on :$PORT"
mkdir -p "$WORK/data1"
setsid env APP_DATA_DIR="$WORK/data1" "$BACKEND" --host 127.0.0.1 --port "$PORT" \
  >"$WORK/backend.log" 2>&1 &
PIDS+=($!)
wait_status "$PORT" "${PIDS[-1]}" "$WORK/backend.log"
kill -- "-${PIDS[-1]}" 2>/dev/null || true
wait "${PIDS[-1]}" 2>/dev/null || true  # gone before the launch test looks for a backend

if [ "${SKIP_LAUNCH:-0}" = 1 ]; then
  echo "==> Skipping the AppImage launch (SKIP_LAUNCH=1)"
  exit 0
fi
command -v xvfb-run >/dev/null || { echo "xvfb-run not found — apt install xvfb (or SKIP_LAUNCH=1)" >&2; exit 1; }

echo "==> Launching the AppImage under Xvfb"
# A private data dir (the shell passes app_data_dir as APP_DATA_DIR) and session bus.
mkdir -p "$WORK/xdg-data"
launch=(xvfb-run -a "$APPIMAGE")
command -v dbus-run-session >/dev/null && launch=(dbus-run-session -- "${launch[@]}")
setsid env XDG_DATA_HOME="$WORK/xdg-data" "${launch[@]}" >"$WORK/app.log" 2>&1 &
APP_PID=$!
PIDS+=("$APP_PID")

# The shell picks a free port; find the backend it spawned from the AppImage's mount.
bpid=""
for _ in $(seq 60); do
  for pid in $(pgrep -f '/resources/backend/backend --host 127.0.0.1 --port' || true); do
    case "$(readlink "/proc/$pid/exe" 2>/dev/null)" in
      */.mount_*/resources/backend/backend) bpid=$pid; break ;;
    esac
  done
  [ -n "$bpid" ] && break
  kill -0 "$APP_PID" 2>/dev/null || { echo "  ✗ the AppImage exited; log:" >&2; tail -50 "$WORK/app.log" >&2; exit 1; }
  sleep 1
done
[ -n "$bpid" ] || { echo "  ✗ no backend running from the AppImage's mount; log:" >&2; tail -50 "$WORK/app.log" >&2; exit 1; }
port="$(tr '\0' '\n' <"/proc/$bpid/cmdline" | sed -n '/^--port$/{n;p;}')"
echo "    backend pid $bpid on :$port ($(readlink "/proc/$bpid/exe"))"
wait_status "$port" "$bpid" "$WORK/app.log"
echo "==> AppImage OK"
