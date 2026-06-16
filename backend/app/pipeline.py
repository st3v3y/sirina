from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
from sqlmodel import Session, select

from .audio.local import LocalAudioSource
from .bot.chunker import Chunker, PendingChunk
from .bot.client import TranscriptBot
from .config import settings
from .db import engine
from .llm.ollama_client import OllamaClient, render
from .models import Meeting, PromptTemplate, QAMessage, Segment, Summary
from .runtime import runtime
from .transcribe.whisper import FasterWhisperWorker

log = logging.getLogger(__name__)


@dataclass(slots=True)
class _ActiveMeeting:
    meeting_id: int
    chunker: Chunker
    whisper_queue: asyncio.Queue[PendingChunk]
    whisper_task: asyncio.Task
    aspects_task: asyncio.Task
    stop_source: Callable[[], Awaitable[None]]
    source: str = "discord"
    last_aspect_segment_id: int = 0
    started_monotonic: float = 0.0


class Pipeline:
    def __init__(
        self,
        bot: TranscriptBot | None,
        whisper: FasterWhisperWorker,
        ollama: OllamaClient,
    ) -> None:
        self.bot = bot
        self.whisper = whisper
        self.ollama = ollama
        self._active: _ActiveMeeting | None = None
        self._lock = asyncio.Lock()

    # ---------- meeting lifecycle ----------

    async def start_meeting(self, channel_id: int | None, title: str | None) -> int:
        if self.bot is None:
            raise RuntimeError("Discord bot is not configured; use start_local_meeting instead")
        async with self._lock:
            self._ensure_idle()
            await self.whisper.load()
            t0 = time.monotonic()
            queue, chunker, on_audio = self._make_chunker(t0)
            guild_id, channel_id_real = await self.bot.start_recording(channel_id, on_audio)

            async def stop_source() -> None:
                assert self.bot is not None
                await self.bot.stop_recording()

            return await self._begin_meeting(
                title=title,
                guild_id=str(guild_id),
                channel_id=str(channel_id_real),
                source="discord",
                t0=t0,
                chunker=chunker,
                queue=queue,
                stop_source=stop_source,
            )

    async def start_local_meeting(
        self, device: str | int | None, label: str | None, title: str | None
    ) -> int:
        async with self._lock:
            self._ensure_idle()
            await self.whisper.load()
            t0 = time.monotonic()
            queue, chunker, on_audio = self._make_chunker(t0)
            loop = asyncio.get_running_loop()
            audio_source = LocalAudioSource(
                device=device,
                label=label or "Room",
                on_audio=on_audio,
                loop=loop,
            )
            audio_source.start()

            async def stop_source() -> None:
                audio_source.stop()

            return await self._begin_meeting(
                title=title,
                guild_id="local",
                channel_id=audio_source.device_name,
                source="local",
                t0=t0,
                chunker=chunker,
                queue=queue,
                stop_source=stop_source,
            )

    def _ensure_idle(self) -> None:
        if self._active is not None:
            raise RuntimeError(
                f"Already recording meeting #{self._active.meeting_id}; stop it first"
            )

    def _make_chunker(
        self, t0: float
    ) -> tuple[asyncio.Queue[PendingChunk], Chunker, Callable[[str, str, np.ndarray], None]]:
        queue: asyncio.Queue[PendingChunk] = asyncio.Queue(maxsize=128)
        chunker = Chunker(t0, queue)

        def on_audio(user_id: str, username: str, samples: np.ndarray) -> None:
            chunker.push(user_id, username, samples)

        return queue, chunker, on_audio

    async def _begin_meeting(
        self,
        *,
        title: str | None,
        guild_id: str,
        channel_id: str,
        source: str,
        t0: float,
        chunker: Chunker,
        queue: asyncio.Queue[PendingChunk],
        stop_source: Callable[[], Awaitable[None]],
    ) -> int:
        with Session(engine) as s:
            m = Meeting(
                title=title,
                guild_id=guild_id,
                channel_id=channel_id,
                status="recording",
                source=source,
            )
            s.add(m)
            s.commit()
            s.refresh(m)
            meeting_id = m.id
        assert meeting_id is not None

        whisper_task = asyncio.create_task(
            self._whisper_consumer(meeting_id, queue), name=f"whisper-{meeting_id}"
        )
        aspects_task = asyncio.create_task(
            self._aspects_loop(meeting_id), name=f"aspects-{meeting_id}"
        )

        self._active = _ActiveMeeting(
            meeting_id=meeting_id,
            chunker=chunker,
            whisper_queue=queue,
            whisper_task=whisper_task,
            aspects_task=aspects_task,
            stop_source=stop_source,
            source=source,
            started_monotonic=t0,
        )

        from .api.ws import manager
        await manager.broadcast_status({
            "bot_connected": bool(self.bot and self.bot.is_ready()),
            "voice_channel": self.bot.current_voice_channel_name() if self.bot else None,
            "ollama_ok": await self.ollama.ping(),
            "whisper_loaded": self.whisper.is_loaded(),
            "model": settings.whisper_model,
        })
        await manager.broadcast_meeting(meeting_id, {"type": "status", "status": "recording"})
        log.info("started meeting %d (source=%s)", meeting_id, source)
        return meeting_id

    async def stop_meeting(self, meeting_id: int, summary_template_id: int | None) -> None:
        async with self._lock:
            active = self._active
            if active is None or active.meeting_id != meeting_id:
                # idempotent: nothing to do
                pass
            else:
                try:
                    await active.stop_source()
                except Exception:
                    log.exception("error stopping audio source")
                active.chunker.flush_all()
                # drain whisper queue
                await active.whisper_queue.join() if False else None  # no-op: queue.join needs task_done plumbing
                # cancel background loops after a short grace
                await asyncio.sleep(0.5)
                active.aspects_task.cancel()
                # give whisper a moment to drain
                deadline = time.monotonic() + 5.0
                while not active.whisper_queue.empty() and time.monotonic() < deadline:
                    await asyncio.sleep(0.1)
                active.whisper_task.cancel()
                self._active = None

        with Session(engine) as s:
            m = s.get(Meeting, meeting_id)
            if m is None:
                return
            if m.status != "ended":
                m.ended_at = datetime.now(timezone.utc)
                m.status = "ended"
                s.add(m)
                s.commit()

        # auto-summary if requested or default
        try:
            tmpl_id = summary_template_id or self._default_template_id("summary")
            if tmpl_id is not None:
                await self.summarize(meeting_id=meeting_id, template_id=tmpl_id)
        except Exception:
            log.exception("auto-summary failed")

        from .api.ws import manager
        await manager.broadcast_meeting(meeting_id, {"type": "status", "status": "ended"})
        log.info("stopped meeting %d", meeting_id)

    # ---------- whisper consumer ----------

    async def _whisper_consumer(self, meeting_id: int, queue: asyncio.Queue[PendingChunk]) -> None:
        from .api.ws import manager
        while True:
            chunk = await queue.get()
            try:
                audio_dur = chunk.pcm.size / 16000.0
                t0 = time.monotonic()
                text = await self.whisper.transcribe(chunk.pcm)
                wall = time.monotonic() - t0
                qsize = queue.qsize()
                log.info(
                    "whisper: audio=%.1fs wall=%.2fs ratio=%.2fx qlen=%d",
                    audio_dur,
                    wall,
                    wall / max(audio_dur, 1e-3),
                    qsize,
                )
                if not text or not text.strip():
                    continue
                # Heuristic: drop common whisper-on-silence hallucinations
                if text.strip().lower() in {"thanks for watching!", "you", ".", "thank you."}:
                    continue
                with Session(engine) as s:
                    seg = Segment(
                        meeting_id=meeting_id,
                        discord_user_id=chunk.user_id,
                        username=chunk.username,
                        start_ts=chunk.start_ts,
                        end_ts=chunk.end_ts,
                        text=text,
                    )
                    s.add(seg)
                    s.commit()
                    s.refresh(seg)
                await manager.broadcast_meeting(
                    meeting_id,
                    {
                        "type": "segment",
                        "segment": {
                            "id": seg.id,
                            "meeting_id": meeting_id,
                            "discord_user_id": seg.discord_user_id,
                            "username": seg.username,
                            "start_ts": seg.start_ts,
                            "end_ts": seg.end_ts,
                            "text": seg.text,
                        },
                    },
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("whisper consumer error")
            finally:
                queue.task_done()

    # ---------- aspects loop ----------

    async def _aspects_loop(self, meeting_id: int) -> None:
        from .api.ws import manager
        interval = max(15, int(settings.aspects_interval_seconds))
        last_seen_id = 0
        previous_aspects = ""
        await asyncio.sleep(interval)  # let some content build first
        while True:
            try:
                with Session(engine) as s:
                    new_segs = s.exec(
                        select(Segment)
                        .where(Segment.meeting_id == meeting_id)
                        .where(Segment.id > last_seen_id)  # type: ignore[operator]
                        .order_by(Segment.start_ts)
                    ).all()
                if new_segs:
                    new_transcript = "\n".join(f"{seg.username}: {seg.text}" for seg in new_segs)
                    tmpl = self._template_by_kind("aspects")
                    if tmpl is not None:
                        prompt = render(
                            tmpl.body,
                            {
                                "previous_aspects": previous_aspects or "(none)",
                                "new_transcript": new_transcript,
                            },
                        )
                        response = await self.ollama.generate(prompt)
                        if response:
                            with Session(engine) as s:
                                summary = Summary(
                                    meeting_id=meeting_id,
                                    kind="live_aspect",
                                    template_id=tmpl.id,
                                    content=response,
                                )
                                s.add(summary)
                                s.commit()
                                s.refresh(summary)
                            previous_aspects = response
                            await manager.broadcast_meeting(
                                meeting_id,
                                {
                                    "type": "aspect",
                                    "summary": {
                                        "id": summary.id,
                                        "meeting_id": meeting_id,
                                        "kind": "live_aspect",
                                        "template_id": tmpl.id,
                                        "content": summary.content,
                                        "created_at": summary.created_at.isoformat(),
                                    },
                                },
                            )
                    last_seen_id = max(s.id or 0 for s in new_segs)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("aspects loop error")
            await asyncio.sleep(interval)

    # ---------- summarise / ask ----------

    async def summarize(self, meeting_id: int, template_id: int) -> Summary:
        from .api.ws import manager
        with Session(engine) as s:
            tmpl = s.get(PromptTemplate, template_id)
            if tmpl is None:
                raise ValueError(f"template {template_id} not found")
            segs = s.exec(
                select(Segment).where(Segment.meeting_id == meeting_id).order_by(Segment.start_ts)
            ).all()
        transcript = "\n".join(f"{seg.username}: {seg.text}" for seg in segs)
        prompt = render(tmpl.body, {"transcript": transcript})
        response = await self.ollama.generate(prompt)
        with Session(engine) as s:
            summary = Summary(
                meeting_id=meeting_id,
                kind="full",
                template_id=template_id,
                content=response,
            )
            s.add(summary)
            s.commit()
            s.refresh(summary)
        await manager.broadcast_meeting(
            meeting_id,
            {
                "type": "full_summary",
                "summary": {
                    "id": summary.id,
                    "meeting_id": meeting_id,
                    "kind": "full",
                    "template_id": template_id,
                    "content": summary.content,
                    "created_at": summary.created_at.isoformat(),
                },
            },
        )
        return summary

    async def ask(self, meeting_id: int, question: str, template_id: int | None) -> str:
        from .api.ws import manager
        with Session(engine) as s:
            tmpl_id = template_id or self._default_template_id("qa")
            if tmpl_id is None:
                raise ValueError("no qa template available")
            tmpl = s.get(PromptTemplate, tmpl_id)
            if tmpl is None:
                raise ValueError("qa template not found")
            segs = s.exec(
                select(Segment).where(Segment.meeting_id == meeting_id).order_by(Segment.start_ts)
            ).all()
            history = s.exec(
                select(QAMessage).where(QAMessage.meeting_id == meeting_id).order_by(QAMessage.created_at)
            ).all()
        transcript = "\n".join(f"{seg.username}: {seg.text}" for seg in segs)
        qa_history = "\n".join(f"{m.role.upper()}: {m.content}" for m in history)
        prompt = render(
            tmpl.body,
            {
                "transcript": transcript,
                "qa_history": qa_history or "(none)",
                "question": question,
            },
        )
        response = await self.ollama.generate(prompt)
        with Session(engine) as s:
            user_msg = QAMessage(meeting_id=meeting_id, role="user", content=question)
            ai_msg = QAMessage(meeting_id=meeting_id, role="assistant", content=response or "(no answer)")
            s.add(user_msg)
            s.add(ai_msg)
            s.commit()
            s.refresh(user_msg)
            s.refresh(ai_msg)
        for msg in (user_msg, ai_msg):
            await manager.broadcast_meeting(
                meeting_id,
                {
                    "type": "qa",
                    "message": {
                        "id": msg.id,
                        "meeting_id": meeting_id,
                        "role": msg.role,
                        "content": msg.content,
                        "created_at": msg.created_at.isoformat(),
                    },
                },
            )
        return response

    # ---------- helpers ----------

    def _default_template_id(self, kind: str) -> int | None:
        with Session(engine) as s:
            t = s.exec(
                select(PromptTemplate).where(PromptTemplate.kind == kind).where(PromptTemplate.is_default == True)  # noqa: E712
            ).first()
            return t.id if t else None

    def _template_by_kind(self, kind: str) -> PromptTemplate | None:
        with Session(engine) as s:
            return s.exec(
                select(PromptTemplate).where(PromptTemplate.kind == kind).where(PromptTemplate.is_default == True)  # noqa: E712
            ).first()
