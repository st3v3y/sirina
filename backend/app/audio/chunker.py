from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

import numpy as np
import torch
from silero_vad import VADIterator, load_silero_vad

from ..config import settings

log = logging.getLogger(__name__)

FRAME_SAMPLES = 512  # silero v5 expects 512 samples @ 16 kHz (= 32 ms)
SR = 16_000


@dataclass(slots=True)
class PendingChunk:
    user_id: str
    username: str
    pcm: np.ndarray
    start_ts: float
    end_ts: float


@dataclass(slots=True)
class _UserState:
    vad: VADIterator
    buffer: list[np.ndarray] = field(default_factory=list)
    samples_buffered: int = 0
    last_voice_t: float = 0.0
    chunk_started_at: float | None = None  # meeting-relative seconds
    leftover: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.float32))


class Chunker:
    """Per-meeting chunker. Feeds audio frame-by-frame into silero VAD,
    emits a `PendingChunk` per user when trailing silence or a hard cap is hit."""

    def __init__(self, meeting_started_monotonic: float, out_queue: asyncio.Queue[PendingChunk]) -> None:
        self._model = load_silero_vad()
        self._states: dict[str, _UserState] = {}
        self._users: dict[str, str] = {}  # user_id -> username
        self._t0 = meeting_started_monotonic
        self._out = out_queue
        self._max_samples = int(settings.chunk_max_seconds * SR)
        self._silence_samples_target = int(settings.chunk_silence_ms * SR / 1000)

    def _now_rel(self) -> float:
        return time.monotonic() - self._t0

    def _state(self, user_id: str, username: str) -> _UserState:
        self._users[user_id] = username
        st = self._states.get(user_id)
        if st is None:
            st = _UserState(vad=VADIterator(self._model, sampling_rate=SR, threshold=0.5, min_silence_duration_ms=settings.chunk_silence_ms))
            self._states[user_id] = st
        return st

    def push(self, user_id: str, username: str, samples: np.ndarray) -> None:
        """Called from the asyncio loop with float32 mono 16 kHz samples (any length)."""
        if samples.size == 0:
            return
        st = self._state(user_id, username)
        # Stitch leftover + new
        audio = np.concatenate([st.leftover, samples]) if st.leftover.size else samples
        # Process whole 512-sample frames
        n_frames = audio.size // FRAME_SAMPLES
        consumed = n_frames * FRAME_SAMPLES
        for i in range(n_frames):
            frame = audio[i * FRAME_SAMPLES : (i + 1) * FRAME_SAMPLES]
            self._process_frame(st, user_id, username, frame)
        st.leftover = audio[consumed:].astype(np.float32, copy=False)

    def _process_frame(self, st: _UserState, user_id: str, username: str, frame: np.ndarray) -> None:
        tensor = torch.from_numpy(frame).float()
        event = st.vad(tensor, return_seconds=False)
        is_speech = st.vad.triggered  # silero internal flag — True while inside a speech region

        st.buffer.append(frame)
        st.samples_buffered += FRAME_SAMPLES
        if st.chunk_started_at is None and st.samples_buffered > 0:
            st.chunk_started_at = self._now_rel() - st.samples_buffered / SR

        if is_speech:
            st.last_voice_t = self._now_rel()

        end_marker = isinstance(event, dict) and "end" in event
        too_long = st.samples_buffered >= self._max_samples

        if end_marker or too_long:
            if st.samples_buffered >= FRAME_SAMPLES * 4:  # at least ~128 ms
                self._flush(st, user_id, username)
            else:
                st.buffer.clear()
                st.samples_buffered = 0
                st.chunk_started_at = None

    def _flush(self, st: _UserState, user_id: str, username: str) -> None:
        if not st.buffer:
            return
        pcm = np.concatenate(st.buffer).astype(np.float32)
        start_ts = st.chunk_started_at if st.chunk_started_at is not None else 0.0
        end_ts = self._now_rel()
        chunk = PendingChunk(
            user_id=user_id,
            username=username,
            pcm=pcm,
            start_ts=max(0.0, start_ts),
            end_ts=end_ts,
        )
        try:
            self._out.put_nowait(chunk)
        except asyncio.QueueFull:
            log.warning("whisper queue full; dropping chunk for %s", username)
        st.buffer.clear()
        st.samples_buffered = 0
        st.chunk_started_at = None

    def flush_all(self) -> None:
        for user_id, st in self._states.items():
            self._flush(st, user_id, self._users.get(user_id, "?"))
