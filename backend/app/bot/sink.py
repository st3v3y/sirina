from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable

import numpy as np
from discord import User
from discord.ext.voice_recv import AudioSink, VoiceData

log = logging.getLogger(__name__)

# Discord voice gives us 48 kHz stereo 16-bit signed PCM in 20 ms frames.
DISCORD_SR = 48_000
TARGET_SR = 16_000


@dataclass(slots=True)
class AudioChunk:
    discord_user_id: str
    username: str
    pcm: np.ndarray  # float32 mono 16 kHz
    start_ts: float
    end_ts: float


class PerUserPCMSink(AudioSink):
    """Receives per-user PCM packets, downmixes to mono, resamples to 16 kHz,
    and pushes (user_id, username, float32_chunk) tuples thread-safely into an asyncio
    callback. The chunker downstream owns buffering and VAD."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        on_audio: Callable[[str, str, np.ndarray], None],
    ) -> None:
        super().__init__()
        self._loop = loop
        self._on_audio = on_audio

    def wants_opus(self) -> bool:
        return False

    def write(self, user: User | None, data: VoiceData) -> None:  # called from reader thread
        if user is None or not data.pcm:
            return
        try:
            pcm_i16 = np.frombuffer(data.pcm, dtype=np.int16)
            if pcm_i16.size == 0:
                return
            # Stereo interleaved -> mono
            stereo = pcm_i16.reshape(-1, 2)
            mono = stereo.mean(axis=1)
            # int16 -> float32 normalised
            mono_f = (mono / 32768.0).astype(np.float32)
            # Resample 48k -> 16k (1:3 decimation; do it cheaply via polyphase)
            from scipy.signal import resample_poly

            mono_16k = resample_poly(mono_f, TARGET_SR, DISCORD_SR).astype(np.float32)
            self._loop.call_soon_threadsafe(
                self._on_audio, str(user.id), user.display_name or user.name, mono_16k
            )
        except Exception:
            log.exception("sink write failure")

    def cleanup(self) -> None:
        pass
