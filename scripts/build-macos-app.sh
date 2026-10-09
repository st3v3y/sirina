#!/usr/bin/env bash
# Build the Sirina macOS app: freeze the Python backend, embed it as a
# Tauri sidecar, build the .app/.dmg, and ad-hoc sign so it launches unsigned.
#
# Prereqs (one-time, on your Mac):
#   - Rust + Tauri CLI:  https://tauri.app/start/prerequisites/  (`cargo install tauri-cli --version '^2'`)
#   - PyInstaller:       cd backend && uv add --dev pyinstaller
#   - Node >= 18:        nvm use 22
#
# This script is scaffolding — adjust paths/targets as needed; it has not been run here.
#
# Speech work (WhisperKit transcription, SpeakerKit speaker splitting, Apple on-device
# draft/captions) is in the native speech-engine helper; models download on first use.
# There are no optional heavy variants any more.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

for arg in "$@"; do
  case "$arg" in
    --mlx|--diarization) echo "note: $arg is no longer needed (speech runs in the native helper); ignoring" ;;
    *) echo "unknown flag: $arg"; exit 1 ;;
  esac
done

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
# The Tauri CLI: `cargo tauri` if installed (cargo install tauri-cli --version '^2'),
# else fetched with npx.
tauri() {
  if cargo tauri --version >/dev/null 2>&1; then cargo tauri "$@"; else npx --yes @tauri-apps/cli@^2 "$@"; fi
}
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
if [ "$NODE_MAJOR" -lt 18 ]; then
  echo "  ✗ Node $NODE_MAJOR is too old (Vite needs >= 18) — run:  nvm use 22"
  missing=1
fi
# Fail fast if an explicit signing identity won't resolve, rather than building for
# minutes and only failing at codesign with "no identity found".
if [ -n "${CODESIGN_IDENTITY:-}" ]; then
  if ! security find-identity -p codesigning 2>/dev/null | grep -qF "$CODESIGN_IDENTITY"; then
    echo "  ✗ CODESIGN_IDENTITY=\"$CODESIGN_IDENTITY\" is not a valid code-signing identity."
    echo "    Available: $(security find-identity -p codesigning 2>/dev/null | grep -oE '\"[^\"]+\"' | paste -sd ', ' -)"
    echo "    Create a self-signed 'Code Signing' cert (see docs/PACKAGING.md), or use one above."
    missing=1
  fi
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

cd "$ROOT/backend"
echo "==> Freezing backend with PyInstaller"
uv run python -m PyInstaller packaging/backend.spec --noconfirm --distpath dist --workpath build

echo "==> Placing onedir backend into Tauri resources"
RES_DIR="$ROOT/frontend/src-tauri/resources"
rm -rf "$RES_DIR/backend"
mkdir -p "$RES_DIR"
cp -R "$ROOT/backend/dist/backend" "$RES_DIR/backend"   # -> resources/backend/{backend, _internal/…}
chmod +x "$RES_DIR/backend/backend"

echo "==> Building native system-audio capture sidecar"
"$ROOT/native/system-audio-capture/build.sh"
mkdir -p "$RES_DIR"
cp "$ROOT/native/system-audio-capture/build/system-audio-capture" "$RES_DIR/system-audio-capture"
chmod +x "$RES_DIR/system-audio-capture"

echo "==> Building native speech helper (WhisperKit / SpeakerKit / Apple speech)"
"$ROOT/native/speech-engine/build.sh"
cp "$ROOT/native/speech-engine/build/speech-engine" "$RES_DIR/speech-engine"
chmod +x "$RES_DIR/speech-engine"

echo "==> Building the Tauri app"
cd "$ROOT/frontend/src-tauri" && tauri build

APP="$ROOT/frontend/src-tauri/target/release/bundle/macos/Sirina.app"
# Sign with a stable identity so macOS persists the Screen Recording (TCC) grant across
# launches and rebuilds. Ad-hoc ("-") works to launch but TCC re-prompts every time.
# Set CODESIGN_IDENTITY to a *personal self-signed* "Code Signing" certificate
# (Keychain Access → Certificate Assistant → Create a Certificate). We deliberately do
# NOT auto-pick an "Apple Development" identity — that may be a company/work cert.
# Resolve the identity: explicit CODESIGN_IDENTITY → a single local self-signed
# code-signing cert (Apple Development/Distribution/Developer ID are skipped — they may be
# a company/work cert) → ad-hoc "-". Ad-hoc launches fine but re-prompts for permissions.
IDENTITY="${CODESIGN_IDENTITY:-}"
if [ -z "$IDENTITY" ]; then
  CANDIDATES="$(security find-identity -p codesigning 2>/dev/null \
    | grep -oE '"[^"]+"' | tr -d '"' \
    | grep -viE 'Apple Development|Apple Distribution|Developer ID|3rd Party' || true)"
  if [ "$(printf '%s\n' "$CANDIDATES" | sed '/^$/d' | wc -l | tr -d ' ')" = "1" ]; then
    IDENTITY="$(printf '%s\n' "$CANDIDATES" | sed '/^$/d')"
    echo "  Using code-signing identity: $IDENTITY (override with CODESIGN_IDENTITY)"
  fi
fi
IDENTITY="${IDENTITY:--}"
if [ "$IDENTITY" = "-" ]; then
  echo "  ⚠  Ad-hoc signing — macOS will RE-PROMPT for Screen Recording on every launch."
  echo "     Create a self-signed 'Code Signing' cert and set CODESIGN_IDENTITY so the grant"
  echo "     persists. See docs/PACKAGING.md."
fi
BUNDLE_ID="$(sed -n 's/.*"identifier"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$ROOT/frontend/src-tauri/tauri.conf.json" | head -1)"
echo "==> Codesigning $APP with: $IDENTITY"
# inside-out: nested binaries first, then the bundle (no hardened runtime — PyInstaller libs).
# The capture sidecar is signed with the APP's bundle identifier so macOS TCC treats its
# ScreenCaptureKit call as the same client as the app — otherwise the Screen Recording
# grant doesn't cover it and native capture never becomes available.
codesign --force --timestamp=none --identifier "$BUNDLE_ID" --sign "$IDENTITY" "$APP/Contents/Resources/resources/system-audio-capture"
# Same for the speech helper: on-device speech recognition permission belongs to the app.
codesign --force --timestamp=none --identifier "$BUNDLE_ID" --sign "$IDENTITY" "$APP/Contents/Resources/resources/speech-engine"
# Onedir exposes the backend's dylibs/.so as individual files — every Mach-O must be signed
# or the (signed) app won't launch. Sign them all, then the backend exe, then the bundle.
find "$APP/Contents/Resources/resources/backend" -type f \( -name "*.so" -o -name "*.dylib" -o -perm +111 \) -print0 \
  | while IFS= read -r -d '' f; do codesign --force --timestamp=none --sign "$IDENTITY" "$f" >/dev/null 2>&1 || true; done
codesign --force --timestamp=none --sign "$IDENTITY" "$APP/Contents/Resources/resources/backend/backend"
codesign --force --timestamp=none --sign "$IDENTITY" "$APP"

# The DMG is made here, from the signed app (a Tauri-built DMG would hold the app before
# signing). The name has no version so the README can link to releases/latest/download/.
DMG_DIR="$ROOT/frontend/src-tauri/target/release/bundle/dmg"
DMG="$DMG_DIR/Sirina-macOS-arm64.dmg"
echo "==> Creating $DMG"
STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
mkdir -p "$DMG_DIR"
rm -f "$DMG"
# hdiutil sometimes fails with "Resource busy" on CI runners; a retry is enough.
for attempt in 1 2 3; do
  hdiutil create -volname Sirina -srcfolder "$STAGE" -ov -format UDZO "$DMG" && break
  [ "$attempt" = 3 ] && exit 1
  sleep 5
done
rm -rf "$STAGE"

cat <<EOF

Done. App: $APP
DMG:  $DMG

First launch (unsigned): right-click the app → Open (once), or:
    xattr -dr com.apple.quarantine "$APP"

The app needs a local Ollama running (http://localhost:11434).
EOF
