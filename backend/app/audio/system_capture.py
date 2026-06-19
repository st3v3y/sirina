"""Locate and probe the native macOS system-audio capture sidecar.

The sidecar (a Swift/ScreenCaptureKit binary, see `native/system-audio-capture/`) emits
48 kHz mono s16le PCM on stdout. It's available only where the binary exists AND has the
Screen Recording permission (i.e. the packaged desktop app) — elsewhere the recorder
falls back to the BlackHole device path.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from ..config import settings

log = logging.getLogger(__name__)

# Dev build location (produced by native/system-audio-capture/build.sh).
_DEV_PATH = (
    Path(__file__).resolve().parents[3]
    / "native"
    / "system-audio-capture"
    / "build"
    / "system-audio-capture"
)


def sidecar_path() -> str | None:
    """The sidecar binary path: explicit config/env first, then the dev build."""
    if settings.system_audio_sidecar and Path(settings.system_audio_sidecar).exists():
        return settings.system_audio_sidecar
    if _DEV_PATH.exists():
        return str(_DEV_PATH)
    return None


def native_available() -> bool:
    """True if the sidecar exists and `--probe` exits 0 (runnable + permission granted).

    Not cached: Screen Recording permission can be granted/revoked at runtime, and the
    probe is cheap (the sidecar exits immediately on success or denial)."""
    path = sidecar_path()
    if not path:
        return False
    try:
        result = subprocess.run([path, "--probe"], capture_output=True, timeout=10)
    except Exception:
        log.warning("native capture probe failed to run (path=%s)", path, exc_info=True)
        return False
    if result.returncode != 0:
        log.info(
            "native system-audio capture unavailable (exit %d): %s",
            result.returncode,
            result.stderr.decode(errors="replace").strip(),
        )
        return False
    return True


def spawn() -> subprocess.Popen:
    """Start the sidecar; its stdout yields raw 48 kHz mono s16le PCM."""
    path = sidecar_path()
    if not path:
        raise RuntimeError("native system-audio sidecar not found")
    return subprocess.Popen(path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)


def kill_stale() -> None:
    """Best-effort: kill any orphaned sidecar processes left by a prior crash. Safe to
    call at startup (no recording is active yet, so we won't kill a live capture)."""
    path = sidecar_path()
    if not path:
        return
    try:
        subprocess.run(["pkill", "-f", Path(path).name], capture_output=True, timeout=5)
    except Exception:
        log.debug("kill_stale failed", exc_info=True)
