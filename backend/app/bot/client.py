from __future__ import annotations

import asyncio
import logging
from typing import Callable

import discord
from discord.ext.voice_recv import VoiceRecvClient

from ..config import settings
from .sink import PerUserPCMSink

log = logging.getLogger(__name__)


# Defensive shim: some py-cord builds (and older discord.py paths) called
# `self.sink = None` in VoiceClient.__init__, which the extension's strict
# setter would reject. With discord.py this never fires today; harmless safety net.
_orig_sink_setter = VoiceRecvClient.sink.fset  # type: ignore[union-attr]


def _patched_sink_setter(self, value):  # type: ignore[no-untyped-def]
    if value is None:
        return
    _orig_sink_setter(self, value)  # type: ignore[misc]


VoiceRecvClient.sink = VoiceRecvClient.sink.setter(_patched_sink_setter)  # type: ignore[assignment]


# Work around discord-ext-voice-recv (0.5.2a179): a single corrupted opus
# packet propagates `OpusError` out of the PacketRouter daemon thread, which
# kills the audio-receive loop for the rest of the session. Wrap pop_data
# to drop bad packets and keep the thread alive.
from discord.opus import OpusError  # noqa: E402
from discord.ext.voice_recv.opus import PacketDecoder  # noqa: E402

_orig_pop_data = PacketDecoder.pop_data


def _safe_pop_data(self, *, timeout: float = 0):  # type: ignore[no-untyped-def]
    try:
        return _orig_pop_data(self, timeout=timeout)
    except OpusError as e:
        log.warning("opus decode error, dropping packet: %s", e)
        return None


PacketDecoder.pop_data = _safe_pop_data  # type: ignore[assignment]


class TranscriptBot(discord.Client):
    """Discord bot that joins a single voice channel at a time and pipes per-user audio
    into a callback. Lifecycle (start_recording / stop_recording) is driven by the API."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = False
        intents.voice_states = True
        intents.members = True
        super().__init__(intents=intents)
        self._voice: VoiceRecvClient | None = None
        self._on_audio: Callable[[str, str, "np.ndarray"], None] | None = None  # type: ignore
        self._ready_evt = asyncio.Event()

    async def on_ready(self) -> None:
        log.info("bot logged in as %s (id=%s)", self.user, self.user.id if self.user else "?")
        self._ready_evt.set()

    async def wait_until_ready_evt(self, timeout: float = 30.0) -> None:
        await asyncio.wait_for(self._ready_evt.wait(), timeout=timeout)

    def is_ready(self) -> bool:  # type: ignore[override]
        return self._ready_evt.is_set() and super().is_ready()

    def current_voice_channel_name(self) -> str | None:
        if self._voice is None or self._voice.channel is None:
            return None
        return self._voice.channel.name

    async def start_recording(
        self,
        channel_id: int | None,
        on_audio: Callable[[str, str, "np.ndarray"], None],  # type: ignore
    ) -> tuple[int, int]:
        """Joins a voice channel and attaches the sink. Returns (guild_id, channel_id)."""
        guild_id = int(settings.discord_guild_id) if settings.discord_guild_id else None
        guild = None
        if guild_id is not None:
            guild = self.get_guild(guild_id) or await self.fetch_guild(guild_id)
        else:
            guild = self.guilds[0] if self.guilds else None
        if guild is None:
            raise RuntimeError("No guild configured / accessible")

        VocalChannel = (discord.VoiceChannel, discord.StageChannel)
        channel: discord.VoiceChannel | discord.StageChannel | None = None
        if channel_id is not None:
            ch = guild.get_channel(channel_id)
            if not isinstance(ch, VocalChannel):
                raise RuntimeError(
                    f"Channel {channel_id} is not a voice or stage channel in guild {guild.id}"
                )
            channel = ch
        else:
            channel = next(
                (c for c in guild.channels if isinstance(c, VocalChannel) and len(c.members) > 0),
                None,
            )
            if channel is None:
                channel = next((c for c in guild.channels if isinstance(c, VocalChannel)), None)
            if channel is None:
                raise RuntimeError("No voice or stage channel available")

        if self._voice and self._voice.is_connected():
            await self._voice.disconnect(force=True)

        self._voice = await channel.connect(cls=VoiceRecvClient)
        self._on_audio = on_audio
        loop = asyncio.get_running_loop()
        self._voice.listen(PerUserPCMSink(loop, on_audio))
        log.info("recording in #%s (%d) of %s (%d)", channel.name, channel.id, guild.name, guild.id)
        return guild.id, channel.id

    async def stop_recording(self) -> None:
        if self._voice is None:
            return
        try:
            self._voice.stop_listening()
        except Exception:
            pass
        try:
            await self._voice.disconnect(force=True)
        except Exception:
            log.exception("voice disconnect failed")
        finally:
            self._voice = None
            self._on_audio = None


async def run_bot_in_background(bot: TranscriptBot) -> asyncio.Task:
    if not settings.discord_token:
        raise RuntimeError("DISCORD_TOKEN not configured")

    async def runner() -> None:
        try:
            await bot.start(settings.discord_token)
        except Exception:
            log.exception("bot crashed")

    task = asyncio.create_task(runner(), name="discord-bot")
    return task
