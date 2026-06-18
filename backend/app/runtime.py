"""Process-wide handles for cross-module access (whisper, ollama, ws manager, pipeline)."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .transcribe.engine import TranscriptionEngine
    from .llm.provider import OpenAICompatProvider
    from .api.ws import ConnectionManager
    from .pipeline import Pipeline
    from .recording.recorder import Recorder
    from .processing.job import TranscriptionProcessor
    from .processing.diarize import Diarizer


class Runtime:
    def __init__(self) -> None:
        self.whisper: TranscriptionEngine | None = None
        self.llm: OpenAICompatProvider | None = None
        self.ws: ConnectionManager | None = None
        self.pipeline: Pipeline | None = None
        self.recorder: Recorder | None = None
        self.processor: TranscriptionProcessor | None = None
        self.diarizer: Diarizer | None = None

    async def llm_ok(self) -> bool:
        if self.llm is None:
            return False
        return await self.llm.ping()

    def whisper_loaded(self) -> bool:
        return bool(self.whisper and self.whisper.is_loaded())

    async def rebuild_llm(self) -> None:
        """Rebuild the LLM provider after an AI setting (provider/model/base_url/key)
        changed, so the next summary/answer uses it without a restart. Old client closed."""
        from .llm.provider import build_llm

        old = self.llm
        self.llm = build_llm()
        if self.pipeline is not None:
            self.pipeline.llm = self.llm
        if old is not None:
            await old.close()


runtime = Runtime()
