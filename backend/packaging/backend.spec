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

# Apple-GPU transcription (MLX) — OPT-IN via SIRINA_BUNDLE_MLX=1 (the build script's
# --mlx flag). It roughly triples the backend bundle (~480 MB: mlx dylibs + two copies
# of the 150 MB Metal kernel library + numba→llvmlite + scipy + tiktoken), so the
# default build ships without it; the engine chooser falls back to faster-whisper and
# tells the user via `engine_note` (see app/transcribe/engine.py).
BUNDLE_MLX = os.environ.get("SIRINA_BUNDLE_MLX", "0") == "1"

if BUNDLE_MLX:
    # `mlx` ships the Metal kernel library (mlx/lib/mlx.metallib, ~150 MB) +
    # libmlx.dylib that collect_all gathers. `mlx_whisper` is imported lazily by
    # app/transcribe/mlx.py, so it must be named here for analysis to follow it; that
    # import graph then drags in its real deps — numba (→ llvmlite), scipy
    # (word-timestamp DTW in timing.py) and tiktoken — via their PyInstaller hooks.
    # `torch` is NOT on the transcribe path (only the unused torch_whisper.py imports
    # it), so it's excluded below to keep ~430 MB of CUDA/Torch out of the bundle.
    for pkg in ("mlx", "mlx_whisper", "tiktoken"):
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h

    # mlx locates its Metal kernels (mlx.metallib) at runtime via dladdr — it looks for the
    # file colocated with libmlx.dylib. PyInstaller ships libmlx.dylib at the package path
    # (_internal/mlx/lib/) plus a symlink at _internal/ root. Tauri's resource bundler then
    # DEREFERENCES that symlink into a real file at _internal/ root, so mlx ends up loaded from
    # there and searches _internal/ for the metallib — where there isn't one — and falls back
    # to faster-whisper ("Failed to load the default metallib"). Shipping a second copy of the
    # metallib at the _internal/ root makes the colocated lookup succeed no matter which
    # libmlx dyld picks. Costs ~150 MB; the alternative (un-dereferencing in the bundler) is
    # brittler. See app/transcribe/engine.py for the symptom this prevents.
    import importlib.util as _ilu  # noqa: E402

    _mlx_spec = _ilu.find_spec("mlx")
    if _mlx_spec and _mlx_spec.submodule_search_locations:
        _mlx_dir = list(_mlx_spec.submodule_search_locations)[0]
        _metallib = os.path.join(_mlx_dir, "lib", "mlx.metallib")
        if os.path.exists(_metallib):
            datas += [(_metallib, ".")]  # -> _internal/mlx.metallib (colocated with the root libmlx)

# sounddevice is a single module (not a package); its PortAudio dylib is handled by
# PyInstaller's contrib hook. Just make sure it's imported.
hiddenimports += ["sounddevice"]

# Optional heavy extra — uncomment to bundle (adds hundreds of MB):
#   - diarization: torch, pyannote, lightning_fabric, asteroid_filterbanks
# for pkg in ("torch", "pyannote", "lightning_fabric"):
#     d, b, h = collect_all(pkg); datas += d; binaries += b; hiddenimports += h

hiddenimports += collect_submodules("uvicorn") + ["app.main"]

# Keep torch out: mlx_whisper.torch_whisper imports it but is never used (our path is
# the MLX transcribe()), so excluding both keeps ~430 MB of Torch off the bundle.
excludes = [
    "tkinter",
    "matplotlib",
    "torch",
    "torchaudio",  # dead stub without torch; only the unused torch_whisper.py refs it
    "mlx_whisper.torch_whisper",
]
if not BUNDLE_MLX:
    # Belt & braces: even though nothing collects them, a stray import edge must not
    # drag the MLX chain (incl. numba→llvmlite ~110 MB and scipy ~36 MB — only the MLX
    # resample path uses scipy at runtime) back into the default bundle.
    excludes += ["mlx", "mlx_whisper", "tiktoken", "numba", "llvmlite", "scipy"]

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
