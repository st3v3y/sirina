import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import audio as audio_api
from .api import meetings, status, templates
from .api import debug as debug_api
from .api import ws as ws_api
from .config import settings
from .db import init_db
from .llm.ollama_client import OllamaClient
from .pipeline import Pipeline
from .runtime import runtime
from .transcribe.whisper import FasterWhisperWorker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# The voice-recv extension logs every RTCP sender report at INFO — pure noise, silence it.
logging.getLogger("discord.ext.voice_recv.reader").setLevel(logging.WARNING)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    runtime.whisper = FasterWhisperWorker()
    runtime.ollama = OllamaClient()

    load_task = asyncio.create_task(runtime.whisper.load(), name="whisper-load")

    bot_task: asyncio.Task | None = None
    if settings.discord_token:
        from .bot.client import TranscriptBot, run_bot_in_background

        runtime.bot = TranscriptBot()
        bot_task = await run_bot_in_background(runtime.bot)
    else:
        log.warning("DISCORD_TOKEN missing - bot will not start; local audio source still works")
    runtime.pipeline = Pipeline(runtime.bot, runtime.whisper, runtime.ollama)

    try:
        yield
    finally:
        if runtime.bot is not None:
            try:
                await runtime.bot.stop_recording()
            except Exception:
                pass
            try:
                await runtime.bot.close()
            except Exception:
                pass
        if bot_task is not None:
            bot_task.cancel()
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
app.include_router(meetings.router)
app.include_router(audio_api.router)
app.include_router(debug_api.router)
app.include_router(ws_api.router)


@app.get("/api/hello")
async def hello() -> dict[str, str]:
    return {"message": "hello from live-transcript-bot"}
