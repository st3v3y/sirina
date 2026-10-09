# PyInstaller spec — freeze the FastAPI backend into a single binary for the Tauri sidecar.
#
#   cd backend
#   uv run pyinstaller packaging/backend.spec --noconfirm
#   -> dist/backend/  (onedir: backend + _internal/); test: ./dist/backend/backend --port 8000
#
# Models are NOT bundled — they download to APP_DATA_DIR/models on first run (see the
# model manager, app/speech_models.py).
import glob
import os
import sys

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

# sounddevice is a single module (not a package). On macOS and Windows its wheel ships
# PortAudio, collected by PyInstaller's contrib hook. On Linux it uses the system
# libportaudio.so.2, which a fresh desktop may not have, so bundle the build machine's
# copy (entry.py points sounddevice at it).
hiddenimports += ["sounddevice", "psutil"]
if sys.platform.startswith("linux"):
    import platform

    # This architecture's copy only (a multiarch host may also have e.g. the i386 one).
    _pa = glob.glob(f"/usr/lib/{platform.machine()}-linux-gnu/libportaudio.so.2") + glob.glob(
        "/usr/lib/libportaudio.so.2"
    )
    if not _pa:
        raise SystemExit("libportaudio.so.2 not found: install libportaudio2 before building")
    binaries += [(_pa[0], ".")]

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
# startup cost. The Tauri app bundles `dist/backend/` as a resource (see the
# scripts/build-* scripts + tauri.<platform>.conf.json) and spawns
# `…/resources/backend/backend[.exe]` directly.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # onedir
    name="backend",
    debug=False,
    strip=False,
    upx=False,
    console=True,  # the shell starts it without a console window on Windows
    # macOS builds are Apple Silicon only; elsewhere (and when unset) the host architecture.
    target_arch=os.environ.get("SIRINA_TARGET_ARCH") or ("arm64" if sys.platform == "darwin" else None),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="backend",  # -> dist/backend/{backend, _internal/…}
)
