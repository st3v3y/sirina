#!/usr/bin/env bash
# Build the Meeting Recorder macOS app: freeze the Python backend, embed it as a
# Tauri sidecar, build the .app/.dmg, and ad-hoc sign so it launches unsigned.
#
# Prereqs (one-time, on your Mac):
#   - Rust + Tauri CLI:  https://tauri.app/start/prerequisites/  (`cargo install tauri-cli --version '^2'`)
#   - PyInstaller:       cd backend && uv add --dev pyinstaller
#   - Node >= 18:        nvm use 22
#
# This script is scaffolding — adjust paths/targets as needed; it has not been run here.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# --- Preflight: check the toolchain and explain how to install anything missing ---
missing=0
need() {  # need <command> <install hint>
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "  ✗ $1 not found — $2"
    missing=1
  fi
}
echo "==> Checking prerequisites"
need rustc       "install Rust:  curl https://sh.rustup.rs -sSf | sh   (then restart your shell)"
need cargo       "comes with Rust (rustup)"
need uv          "install uv:    https://docs.astral.sh/uv/getting-started/installation/"
need npm         "install Node >= 18 (e.g. nvm install 22 && nvm use 22)"
if ! cargo tauri --version >/dev/null 2>&1; then
  echo "  ✗ cargo-tauri not found — install it:  cargo install tauri-cli --version '^2'"
  missing=1
fi
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
if [ "$NODE_MAJOR" -lt 18 ]; then
  echo "  ✗ Node $NODE_MAJOR is too old (Vite needs >= 18) — run:  nvm use 22"
  missing=1
fi
if [ "$missing" -ne 0 ]; then
  echo
  echo "Install the items above, then re-run ./scripts/build-macos-app.sh"
  echo "See docs/PACKAGING.md for the full prerequisite list."
  exit 1
fi
echo "  ✓ toolchain present"

TRIPLE="$(rustc -Vv | sed -n 's/host: //p')"   # e.g. aarch64-apple-darwin
SIDECAR_DIR="$ROOT/frontend/src-tauri/binaries"

echo "==> Building frontend"
cd "$ROOT/frontend" && npm run build

echo "==> Freezing backend with PyInstaller"
cd "$ROOT/backend"
uv run pyinstaller packaging/backend.spec --noconfirm --distpath dist --workpath build

echo "==> Placing backend sidecar as backend-$TRIPLE"
mkdir -p "$SIDECAR_DIR"
cp "$ROOT/backend/dist/backend" "$SIDECAR_DIR/backend-$TRIPLE"
chmod +x "$SIDECAR_DIR/backend-$TRIPLE"

echo "==> Building native system-audio capture sidecar"
"$ROOT/native/system-audio-capture/build.sh"
RES_DIR="$ROOT/frontend/src-tauri/resources"
mkdir -p "$RES_DIR"
cp "$ROOT/native/system-audio-capture/build/system-audio-capture" "$RES_DIR/system-audio-capture"
chmod +x "$RES_DIR/system-audio-capture"

echo "==> Building the Tauri app"
cd "$ROOT/frontend" && cargo tauri build

APP="$ROOT/frontend/src-tauri/target/release/bundle/macos/Meeting Recorder.app"
# Sign with a stable identity so macOS persists the Screen Recording (TCC) grant across
# launches and rebuilds. Ad-hoc ("-") works to launch but TCC re-prompts every time.
# Set CODESIGN_IDENTITY to a *personal self-signed* "Code Signing" certificate
# (Keychain Access → Certificate Assistant → Create a Certificate). We deliberately do
# NOT auto-pick an "Apple Development" identity — that may be a company/work cert.
IDENTITY="${CODESIGN_IDENTITY:--}"
BUNDLE_ID="$(sed -n 's/.*"identifier"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$ROOT/frontend/src-tauri/tauri.conf.json" | head -1)"
echo "==> Codesigning $APP with: $IDENTITY"
# inside-out: nested binaries first, then the bundle (no hardened runtime — PyInstaller libs).
# The capture sidecar is signed with the APP's bundle identifier so macOS TCC treats its
# ScreenCaptureKit call as the same client as the app — otherwise the Screen Recording
# grant doesn't cover it and native capture never becomes available.
codesign --force --timestamp=none --identifier "$BUNDLE_ID" --sign "$IDENTITY" "$APP/Contents/Resources/resources/system-audio-capture"
codesign --force --timestamp=none --sign "$IDENTITY" "$APP/Contents/MacOS/backend"
codesign --force --timestamp=none --sign "$IDENTITY" "$APP"

cat <<EOF

Done. App: $APP
DMG:  $ROOT/frontend/src-tauri/target/release/bundle/dmg/

First launch (unsigned): right-click the app → Open (once), or:
    xattr -dr com.apple.quarantine "$APP"

The app needs a local Ollama running (http://localhost:11434).
EOF
