# PyInstaller spec — freeze the FastAPI backend into a single binary for the Tauri sidecar.
#
#   cd backend
#   uv run pyinstaller packaging/backend.spec --noconfirm
#   -> dist/backend/  (onedir: backend + _internal/); test: ./dist/backend/backend --port 8000
#
# Models are NOT bundled — they download to APP_DATA_DIR/models on first run, as in dev.
# The heavy optional packages (diarization, MLX) are commented out; get the minimal
# binary booting first, then enable what you need.
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

# sounddevice is a single module (not a package); its PortAudio dylib is handled by
# PyInstaller's contrib hook. Just make sure it's imported.
hiddenimports += ["sounddevice"]

# Optional heavy extras — uncomment to bundle (each adds hundreds of MB):
#   - diarization: torch, pyannote, lightning_fabric, asteroid_filterbanks
#   - Apple-GPU transcription: mlx, mlx_whisper
# for pkg in ("torch", "pyannote", "lightning_fabric", "mlx", "mlx_whisper"):
#     d, b, h = collect_all(pkg); datas += d; binaries += b; hiddenimports += h

hiddenimports += collect_submodules("uvicorn") + ["app.main"]

a = Analysis(
    [ENTRY],
    pathex=[BACKEND_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # mlx/mlx_whisper get pulled in partially (mlx.py imports them lazily) but aren't
    # usable in the frozen app — exclude them so the packaged build cleanly uses
    # faster-whisper (CPU). (Apple-GPU MLX in the bundle is a separate, deliberate add.)
    excludes=["tkinter", "matplotlib", "mlx", "mlx_whisper"],
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
