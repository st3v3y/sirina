#!/usr/bin/env bash
# Build the Sirina Linux bundles (AppImage + .deb): freeze the Python backend, build the
# Rust system-audio helper, and bundle both into the Tauri app. No signing.
#
# Prereqs (Debian/Ubuntu names):
#   - Rust (rustup), uv, Node >= 18
#   - Tauri's Linux deps: libwebkit2gtk-4.1-dev libgtk-3-dev librsvg2-dev patchelf
#   - libpulse-dev (helper) and libportaudio2 (bundled into the backend)
# The Tauri CLI is used from `cargo tauri` if installed, else fetched with npx.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

missing=0
need() {  # need <command> <install hint>
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "  ✗ $1 not found — $2"
    missing=1
  fi
}
echo "==> Checking prerequisites"
need cargo "install Rust: curl https://sh.rustup.rs -sSf | sh"
need uv    "install uv: https://docs.astral.sh/uv/getting-started/installation/"
need npm   "install Node >= 18"
if ! pkg-config --exists libpulse-simple 2>/dev/null; then
  echo "  ✗ libpulse-simple not found — apt install libpulse-dev"
  missing=1
fi
# The same lookup backend.spec bundles from (this architecture's copy only).
if [ ! -e "/usr/lib/$(uname -m)-linux-gnu/libportaudio.so.2" ] && [ ! -e /usr/lib/libportaudio.so.2 ]; then
  echo "  ✗ libportaudio.so.2 not found — apt install libportaudio2"
  missing=1
fi
[ "$missing" -eq 0 ] || { echo "Install the items above and re-run."; exit 1; }

tauri() {
  if cargo tauri --version >/dev/null 2>&1; then cargo tauri "$@"; else npx --yes @tauri-apps/cli@^2 "$@"; fi
}

echo "==> Building frontend"
cd "$ROOT/frontend" && npm run build

echo "==> Freezing backend with PyInstaller"
cd "$ROOT/backend"
uv run python -m PyInstaller packaging/backend.spec --noconfirm --distpath dist --workpath build

RES_DIR="$ROOT/frontend/src-tauri/resources"
echo "==> Placing backend and helper into Tauri resources"
rm -rf "$RES_DIR"
mkdir -p "$RES_DIR"
cp -R "$ROOT/backend/dist/backend" "$RES_DIR/backend"
chmod +x "$RES_DIR/backend/backend"

"$ROOT/native/system-audio-capture-rs/build.sh"
cp "$ROOT/native/system-audio-capture-rs/target/release/system-audio-capture" "$RES_DIR/system-audio-capture"
chmod +x "$RES_DIR/system-audio-capture"

echo "==> Building the Tauri bundles"
cd "$ROOT/frontend/src-tauri" && tauri build

BUNDLE="$ROOT/frontend/src-tauri/target/release/bundle"
cat <<DONE

Done.
AppImage: $(ls "$BUNDLE"/appimage/*.AppImage 2>/dev/null || echo "(none)")
Debian:   $(ls "$BUNDLE"/deb/*.deb 2>/dev/null || echo "(none)")

Run the AppImage with:  chmod +x Sirina_*.AppImage && ./Sirina_*.AppImage
The app needs a local Ollama (http://localhost:11434) or another AI provider set in Settings.
DONE
