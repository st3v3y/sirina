#!/usr/bin/env bash
# Build the Sirina Linux bundles (.deb and AppImage): freeze the Python backend, build
# the Rust system-audio helper, and bundle both into the Tauri app. No signing.
#
# Prereqs (Debian/Ubuntu names):
#   - Rust (rustup), uv, Node >= 18
#   - Tauri's Linux deps: libwebkit2gtk-4.1-dev libgtk-3-dev librsvg2-dev patchelf
#   - libpulse-dev (helper) and libportaudio2 (bundled into the backend)
#   - squashfs-tools (adds the backend to the AppImage)
# The Tauri CLI is `cargo tauri` if installed, else the frontend's pinned @tauri-apps/cli.
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
need mksquashfs "apt install squashfs-tools"
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
  if cargo tauri --version >/dev/null 2>&1; then cargo tauri "$@"; else npm run --prefix "$ROOT/frontend" tauri -- "$@"; fi
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

BUNDLE="$ROOT/frontend/src-tauri/target/release/bundle"
cd "$ROOT/frontend/src-tauri"

echo "==> Building the app and the .deb"
tauri build --bundles deb

# The AppImage is bundled without the backend, which is added afterwards: Tauri's
# AppImage step runs linuxdeploy over every library in the AppDir, which fails on (and
# would rewrite the rpaths of) the PyInstaller backend's libraries.
echo "==> Bundling the AppImage (without the backend)"
rm -f "$BUNDLE"/appimage/*.AppImage
# linuxdeploy's strip is too old for libraries from newer distros (.relr.dyn); distro
# libraries are stripped already.
export NO_STRIP="${NO_STRIP:-true}"
# Run linuxdeploy (itself an AppImage) without FUSE, for CI runners and containers.
export APPIMAGE_EXTRACT_AND_RUN="${APPIMAGE_EXTRACT_AND_RUN:-1}"
# Absolute: the npm fallback runs the CLI from frontend/, not src-tauri/.
tauri bundle --bundles appimage --config "$ROOT/frontend/src-tauri/tauri.appimage.conf.json" --verbose
unset APPIMAGE_EXTRACT_AND_RUN

echo "==> Adding the backend to the AppImage"
APPIMAGES=("$BUNDLE"/appimage/*.AppImage)
[ -e "${APPIMAGES[0]}" ] || { echo "No AppImage in $BUNDLE/appimage" >&2; exit 1; }
"$ROOT/scripts/appimage-add-backend.sh" "${APPIMAGES[0]}" "$RES_DIR/backend"

cat <<DONE

Done.
Debian:   $(ls "$BUNDLE"/deb/*.deb 2>/dev/null || echo "(none)")
AppImage: ${APPIMAGES[0]}

Install the .deb with:  sudo apt install ./Sirina_*.deb
Or run the AppImage:    chmod +x Sirina_*.AppImage && ./Sirina_*.AppImage
The app needs a local Ollama (http://localhost:11434) or another AI provider set in Settings.
DONE
