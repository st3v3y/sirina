"""PyInstaller entry point: run the FastAPI backend with uvicorn.

The Tauri shell spawns this binary with `--host 127.0.0.1 --port <free-port>` and
sets `APP_DATA_DIR` so the DB, recordings, and model caches live in the per-user
Application Support directory. Run frozen: `./backend --host 127.0.0.1 --port 8000`.
"""
from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(prog="backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    # Import after arg-parsing so a frozen `--help` is fast; app.main wires the app.
    from app.main import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
