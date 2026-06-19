import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .api import audio as audio_api
from .api import chat, llm as llm_api, people, recordings, settings as settings_api, status, tags, templates
from .api import debug as debug_api
from .api import ws as ws_api
from .config import settings
from .db import init_db
from .llm.provider import build_llm
from .pipeline import Pipeline
from .processing.diarize import Diarizer
from .processing.job import TranscriptionProcessor
from .recording.recorder import Recorder
from .runtime import runtime
from .settings_store import load_overrides
from .transcribe.engine import select_engine

logging.basicConfig(
    level=logging.DEBUG if settings.dev else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

# Persist logs to a rotating file under the data dir so issues can be diagnosed after
# the fact (the packaged app's stdout isn't easily accessible). Secrets are never logged.
try:
    from logging.handlers import RotatingFileHandler

    _log_dir = settings.data_dir / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _file_handler = RotatingFileHandler(_log_dir / "sirina.log", maxBytes=2_000_000, backupCount=3)
    _file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(_file_handler)
    log.info("logging to %s", _log_dir / "sirina.log")
except Exception:
    log.warning("could not set up file logging", exc_info=True)
if settings.dev:
    # DEBUG our own code, but keep chatty third-party libs (HTTP/TLS frames,
    # downloads) at INFO so the app's debug logs stay readable.
    for noisy in ("httpcore", "httpx", "urllib3", "huggingface_hub", "filelock", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.INFO)
    log.info("DEV mode: verbose DEBUG logging enabled")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Layer persisted user overrides onto the Settings singleton BEFORE the engine and
    # LLM client are built, so they pick up the stored config.
    load_overrides()

    from .audio import system_capture

    system_capture.kill_stale()  # clean up any orphaned native-capture sidecar
    runtime.whisper = select_engine()
    runtime.llm = build_llm()
    runtime.recorder = Recorder()

    # Whisper is loaded in the background; it is NOT used during recording. Recording
    # itself runs no inference — the transcription processor uses whisper after stop.
    async def _load_whisper() -> None:
        try:
            await runtime.whisper.load()
            runtime.whisper_error = None
        except Exception as e:  # offline / failed download / OOM — surface, don't hang
            runtime.whisper_error = f"{type(e).__name__}: {e}"
            log.exception("whisper model failed to load")

    load_task = asyncio.create_task(_load_whisper(), name="whisper-load")
    runtime.pipeline = Pipeline(runtime.whisper, runtime.llm)

    runtime.diarizer = Diarizer()
    runtime.processor = TranscriptionProcessor(runtime.whisper, runtime.pipeline, runtime.diarizer)
    runtime.processor.start()
    # Recover any recordings left mid-processing (e.g. after a crash/restart).
    await runtime.processor.requeue_pending()

    try:
        yield
    finally:
        if runtime.recorder is not None and runtime.recorder.is_recording():
            try:
                await runtime.recorder.stop()
            except Exception:
                pass
        if runtime.processor is not None:
            runtime.processor.stop()
        if runtime.llm is not None:
            await runtime.llm.close()
        load_task.cancel()


app = FastAPI(title="Sirina", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(templates.router)
app.include_router(status.router)
app.include_router(settings_api.router)
app.include_router(llm_api.router)
app.include_router(recordings.router)
app.include_router(people.router)
app.include_router(chat.router)
app.include_router(tags.router)
app.include_router(audio_api.router)
app.include_router(debug_api.router)
app.include_router(ws_api.router)


@app.get("/api/hello")
async def hello() -> dict[str, str]:
    return {"message": "hello from sirina"}


def _frontend_dir() -> Path | None:
    """The built frontend, served same-origin so the packaged desktop app (Tauri)
    can load the UI over http://127.0.0.1:<port> — avoiding the webview's mixed-content
    block on a tauri:// page fetching http://. Bundled into the PyInstaller binary as
    `frontend_dist`; in a source checkout it's `frontend/dist` (only if built)."""
    if getattr(sys, "frozen", False):
        cand = Path(getattr(sys, "_MEIPASS", ".")) / "frontend_dist"
    else:
        cand = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    return cand if cand.is_dir() else None


_frontend = _frontend_dir()
if _frontend is not None:
    # SPA fallback: serve index.html for any non-API path so client-side routes work.
    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa(full_path: str) -> FileResponse:
        candidate = _frontend / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_frontend / "index.html")

    log.info("serving frontend from %s", _frontend)
