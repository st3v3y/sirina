"""PyInstaller entry point: run the FastAPI backend with uvicorn.

The Tauri shell spawns this binary with `--host 127.0.0.1 --port <free-port>` and
sets `APP_DATA_DIR` so the DB, recordings, and model caches live in the per-user
Application Support directory. Run frozen: `./backend --host 127.0.0.1 --port 8000`.
"""
from __future__ import annotations

import argparse
import faulthandler
import multiprocessing
import os
import signal
import sys

import uvicorn


def _use_bundled_portaudio() -> None:
    """Linux: sounddevice finds PortAudio via `ctypes.util.find_library("portaudio")`,
    which only searches the system. The frozen app bundles libportaudio.so.2 (see
    backend.spec), so point that lookup at the bundled copy when it is there."""
    if not (getattr(sys, "frozen", False) and sys.platform.startswith("linux")):
        return
    bundled = os.path.join(getattr(sys, "_MEIPASS", ""), "libportaudio.so.2")
    if not os.path.exists(bundled):
        return
    import ctypes.util

    system_find = ctypes.util.find_library
    ctypes.util.find_library = lambda name: bundled if name == "portaudio" else system_find(name)


def main() -> None:
    # A dependency starts multiprocessing's resource tracker by re-running sys.executable
    # (this binary) with Python flags; let PyInstaller's runtime hook handle those runs.
    multiprocessing.freeze_support()
    _use_bundled_portaudio()  # before anything imports sounddevice
    # Crash/hang diagnostics for the frozen app (its stdout is captured to a log by the
    # shell): fatal errors dump Python stacks, and `kill -USR1 <pid>` dumps the stacks
    # of a live process — the only practical way to debug a wedge in a bundle.
    faulthandler.enable()
    try:
        faulthandler.register(signal.SIGUSR1, all_threads=True)
    except (AttributeError, ValueError):
        pass  # not available on this platform

    parser = argparse.ArgumentParser(prog="backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    # Import after arg-parsing so a frozen `--help` is fast; app.main wires the app.
    from app.main import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
