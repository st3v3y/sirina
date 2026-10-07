"""Client for the native speech helper (`native/speech-engine`).

One long-running `speech-engine serve` process answers JSON-lines requests on stdio:
final transcription (WhisperKit), speaker splitting (SpeakerKit) and the on-device draft
(Apple SpeechTranscriber). Requests are serialized by a single lock, so the post-stop job
and transcription during recording never run speech work in parallel. If the helper dies,
the next request restarts it once; a second failure is raised to the caller, which falls
back (CPU engine / baseline speakers / no draft).
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from ..config import settings

log = logging.getLogger(__name__)

# Dev build location (produced by native/speech-engine/build.sh).
_DEV_PATH = Path(__file__).resolve().parents[3] / "native" / "speech-engine" / "build" / "speech-engine"


class HelperError(RuntimeError):
    """The helper answered with an error, or could not be reached."""


def helper_path() -> str | None:
    """The helper binary: explicit config/env first, then the dev build."""
    if settings.speech_engine_helper and Path(settings.speech_engine_helper).exists():
        return settings.speech_engine_helper
    if _DEV_PATH.exists():
        return str(_DEV_PATH)
    return None


_probe_cache: dict | None = None


def probe(refresh: bool = False) -> dict:
    """Capabilities of the helper ({} when missing or not runnable, e.g. macOS < 14)."""
    global _probe_cache
    if _probe_cache is not None and not refresh:
        return _probe_cache
    path = helper_path()
    caps: dict = {}
    if path:
        try:
            out = subprocess.run([path, "--probe"], capture_output=True, text=True, timeout=20)
            if out.returncode == 0 and out.stdout.strip():
                caps = json.loads(out.stdout.strip().splitlines()[-1])
        except Exception:
            log.warning("speech helper probe failed", exc_info=True)
    _probe_cache = caps
    return caps


class SpeechHelper:
    """Async client owning the `serve` subprocess."""

    def __init__(self, path: str | None = None, *, timeout_s: float = 1800.0) -> None:
        self._path = path
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._next_id = 0
        self._timeout_s = timeout_s
        # Re-sent after a restart so a crash doesn't lose loaded models.
        self._loads: dict[str, dict] = {}

    @property
    def lock(self) -> asyncio.Lock:
        return self._lock

    def available(self) -> bool:
        return bool(self._path or helper_path())

    async def _ensure_started(self) -> asyncio.subprocess.Process:
        if self._proc is not None and self._proc.returncode is None:
            return self._proc
        path = self._path or helper_path()
        if not path:
            raise HelperError("speech helper not found")
        self._proc = await asyncio.create_subprocess_exec(
            path, "serve",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=64 * 1024 * 1024,  # a 3-minute window with word timings is a long line
        )
        asyncio.create_task(self._drain_stderr(self._proc), name="speech-helper-stderr")
        for req in self._loads.values():  # restore loaded models after a restart
            await self._send(self._proc, req)
        return self._proc

    @staticmethod
    async def _drain_stderr(proc: asyncio.subprocess.Process) -> None:
        assert proc.stderr is not None
        while True:
            line = await proc.stderr.readline()
            if not line:
                return
            log.info("speech-engine: %s", line.decode(errors="replace").rstrip())

    async def _send(self, proc: asyncio.subprocess.Process, req: dict) -> dict:
        assert proc.stdin is not None and proc.stdout is not None
        self._next_id += 1
        payload = {**req, "id": self._next_id}
        proc.stdin.write((json.dumps(payload) + "\n").encode())
        await proc.stdin.drain()
        while True:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=self._timeout_s)
            if not line:
                raise HelperError("speech helper exited")
            resp = json.loads(line)
            if resp.get("id") == payload["id"]:
                break
        if not resp.get("ok"):
            raise HelperError(str(resp.get("error") or "speech helper error"))
        return resp

    async def request(self, cmd: str, **fields: Any) -> dict:
        """Send one request (serialized). Restarts a dead helper once before giving up."""
        req = {"cmd": cmd, **fields}
        async with self._lock:
            for attempt in (1, 2):
                try:
                    proc = await self._ensure_started()
                    resp = await self._send(proc, req)
                    if cmd.startswith("load_"):
                        self._loads[cmd] = req
                    return resp
                except HelperError as e:
                    if "exited" not in str(e) or attempt == 2:
                        raise
                    log.warning("speech helper exited during %s; restarting once", cmd)
                except (BrokenPipeError, ConnectionResetError, asyncio.IncompleteReadError):
                    if attempt == 2:
                        raise HelperError(f"speech helper failed during {cmd}")
                    log.warning("speech helper pipe broke during %s; restarting once", cmd)
                self._kill()
        raise HelperError("unreachable")

    def _kill(self) -> None:
        if self._proc is not None and self._proc.returncode is None:
            try:
                self._proc.kill()
            except ProcessLookupError:
                pass
        self._proc = None

    async def close(self) -> None:
        proc = self._proc
        self._kill()
        if proc is not None:
            try:
                await asyncio.wait_for(proc.wait(), timeout=3)
            except Exception:
                pass


_shared: SpeechHelper | None = None


def shared_helper() -> SpeechHelper:
    """The process-wide helper (one model set, one request lock)."""
    global _shared
    if _shared is None:
        _shared = SpeechHelper()
    return _shared
