"""Process-wide handles for cross-module access (bot, whisper, ollama, ws manager)."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .bot.client import TranscriptBot
    from .transcribe.whisper import FasterWhisperWorker
    from .llm.ollama_client import OllamaClient
    from .api.ws import ConnectionManager
    from .pipeline import Pipeline


class Runtime:
    def __init__(self) -> None:
        self.bot: TranscriptBot | None = None
        self.whisper: FasterWhisperWorker | None = None
        self.ollama: OllamaClient | None = None
        self.ws: ConnectionManager | None = None
        self.pipeline: Pipeline | None = None

    def bot_connected(self) -> bool:
        return bool(self.bot and self.bot.is_ready())

    def voice_channel_name(self) -> str | None:
        if self.bot is None:
            return None
        return self.bot.current_voice_channel_name()

    async def ollama_ok(self) -> bool:
        if self.ollama is None:
            return False
        return await self.ollama.ping()

    def whisper_loaded(self) -> bool:
        return bool(self.whisper and self.whisper.is_loaded())


runtime = Runtime()
