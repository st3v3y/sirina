import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import audio as audio_api
from .api import chat, people, recordings, status, tags, templates
from .api import debug as debug_api
from .api import ws as ws_api
from .config import settings
from .db import init_db
from .llm.ollama_client import OllamaClient
from .pipeline import Pipeline
from .processing.diarize import Diarizer
from .processing.job import TranscriptionProcessor
from .recording.recorder import Recorder
from .runtime import runtime
from .transcribe.engine import select_engine

logging.basicConfig(
    level=logging.DEBUG if settings.dev else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)
if settings.dev:
    # DEBUG our own code, but keep chatty third-party libs (HTTP/TLS frames,
    # downloads) at INFO so the app's debug logs stay readable.
    for noisy in ("httpcore", "httpx", "urllib3", "huggingface_hub", "filelock", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.INFO)
    log.info("DEV mode: verbose DEBUG logging enabled")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    runtime.whisper = select_engine()
    runtime.ollama = OllamaClient()
    runtime.recorder = Recorder()

    # Whisper is loaded in the background; it is NOT used during recording. Recording
    # itself runs no inference — the transcription processor uses whisper after stop.
    load_task = asyncio.create_task(runtime.whisper.load(), name="whisper-load")
    runtime.pipeline = Pipeline(runtime.whisper, runtime.ollama)

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
        if runtime.ollama is not None:
            await runtime.ollama.close()
        load_task.cancel()


app = FastAPI(title="Live Transcript Bot", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(templates.router)
app.include_router(status.router)
app.include_router(recordings.router)
app.include_router(people.router)
app.include_router(chat.router)
app.include_router(tags.router)
app.include_router(audio_api.router)
app.include_router(debug_api.router)
app.include_router(ws_api.router)


@app.get("/api/hello")
async def hello() -> dict[str, str]:
    return {"message": "hello from live-transcript-bot"}
