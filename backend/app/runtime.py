"""Process-wide handles for cross-module access (whisper, ollama, ws manager, pipeline)."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .transcribe.engine import TranscriptionEngine
    from .llm.ollama_client import OllamaClient
    from .api.ws import ConnectionManager
    from .pipeline import Pipeline
    from .recording.recorder import Recorder
    from .processing.job import TranscriptionProcessor
    from .processing.diarize import Diarizer


class Runtime:
    def __init__(self) -> None:
        self.whisper: TranscriptionEngine | None = None
        self.ollama: OllamaClient | None = None
        self.ws: ConnectionManager | None = None
        self.pipeline: Pipeline | None = None
        self.recorder: Recorder | None = None
        self.processor: TranscriptionProcessor | None = None
        self.diarizer: Diarizer | None = None

    async def ollama_ok(self) -> bool:
        if self.ollama is None:
            return False
        return await self.ollama.ping()

    def whisper_loaded(self) -> bool:
        return bool(self.whisper and self.whisper.is_loaded())

    async def rebuild_llm(self) -> None:
        """Rebuild the LLM client after an AI setting (host/model) changed, so the next
        summary/answer uses the new config without a restart. The old client is closed."""
        from .llm.ollama_client import OllamaClient

        old = self.ollama
        self.ollama = OllamaClient()
        if self.pipeline is not None:
            self.pipeline.ollama = self.ollama
        if old is not None:
            await old.close()


runtime = Runtime()
