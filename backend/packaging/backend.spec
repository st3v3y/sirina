# PyInstaller spec — freeze the FastAPI backend into a single binary for the Tauri sidecar.
#
#   cd backend
#   uv run pyinstaller packaging/backend.spec --noconfirm
#   -> dist/backend/  (onedir: backend + _internal/); test: ./dist/backend/backend --port 8000
#
# Models are NOT bundled — they download to APP_DATA_DIR/models on first run (see the
# model manager, app/speech_models.py).
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

# Paths are resolved relative to this spec file (SPECPATH = backend/packaging),
# so `app` is importable from the backend root regardless of the working dir.
BACKEND_ROOT = os.path.dirname(SPECPATH)  # noqa: F821  (SPECPATH injected by PyInstaller)
ENTRY = os.path.join(SPECPATH, "entry.py")  # noqa: F821

datas, binaries, hiddenimports = [], [], []

# Bundle the built frontend so the backend serves the UI same-origin (the Tauri
# webview loads http://127.0.0.1:<port>, avoiding the mixed-content block on tauri://).
_DIST = os.path.join(os.path.dirname(BACKEND_ROOT), "frontend", "dist")
if os.path.isdir(_DIST):
    datas += [(_DIST, "frontend_dist")]

# Packages that ship data/dylibs we must collect.
for pkg in ("faster_whisper", "ctranslate2", "av"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# Speech work (WhisperKit transcription, SpeakerKit speaker splitting, Apple on-device
# draft/captions) runs in the native `speech-engine` helper, bundled next to this backend
# as a Tauri resource — so no torch / pyannote / MLX here. faster-whisper stays as the
# CPU fallback engine.

# sounddevice is a single module (not a package); its PortAudio dylib is handled by
# PyInstaller's contrib hook. Just make sure it's imported.
hiddenimports += ["sounddevice"]

hiddenimports += collect_submodules("uvicorn") + ["app.main"]

excludes = [
    "tkinter",
    # Belt & braces: nothing imports these any more (speech work lives in the native
    # helper), but a stray import edge must never drag hundreds of MB back in.
    "torch", "torchaudio", "torchcodec", "matplotlib", "lightning", "pytorch_lightning",
    "pyannote", "mlx", "mlx_whisper", "tiktoken", "numba", "llvmlite", "scipy",
]

a = Analysis(
    [ENTRY],
    pathex=[BACKEND_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

# onedir (not onefile): the libs live in a `_internal/` folder next to the exe and are
# NOT re-extracted to a temp dir on every launch — onefile re-extraction was the ~20s
# startup cost. The Tauri app bundles `dist/backend/` as a resource (see build-macos-app.sh
# + tauri.conf.json) and spawns `…/resources/backend/backend` directly.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # onedir
    name="backend",
    debug=False,
    strip=False,
    upx=False,
    console=True,
    target_arch="arm64",  # Apple Silicon
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="backend",  # -> dist/backend/{backend, _internal/…}
)
