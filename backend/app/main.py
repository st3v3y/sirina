import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import audio as audio_api
from .api import recordings, status, templates
from .api import debug as debug_api
from .api import ws as ws_api
from .db import init_db
from .llm.ollama_client import OllamaClient
from .pipeline import Pipeline
from .recording.recorder import Recorder
from .runtime import runtime
from .transcribe.whisper import FasterWhisperWorker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    runtime.whisper = FasterWhisperWorker()
    runtime.ollama = OllamaClient()
    runtime.recorder = Recorder()

    # Whisper is loaded in the background for the (later) transcription job; it is
    # NOT used during recording. Recording itself runs no inference.
    load_task = asyncio.create_task(runtime.whisper.load(), name="whisper-load")
    runtime.pipeline = Pipeline(runtime.whisper, runtime.ollama)

    try:
        yield
    finally:
        if runtime.recorder is not None and runtime.recorder.is_recording():
            try:
                await runtime.recorder.stop()
            except Exception:
                pass
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
app.include_router(audio_api.router)
app.include_router(debug_api.router)
app.include_router(ws_api.router)


@app.get("/api/hello")
async def hello() -> dict[str, str]:
    return {"message": "hello from live-transcript-bot"}
