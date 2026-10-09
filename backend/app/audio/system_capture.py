"""Locate and probe the native system-audio capture helper.

Each platform has its own helper with the same contract (see
`native/system-audio-capture/README.md`): `--probe` exits 0 when capture can run, and
capture mode streams 48 kHz mono s16le PCM on stdout until terminated.

- macOS: Swift / ScreenCaptureKit (`native/system-audio-capture/`). Needs the Screen
  Recording permission, granted to the desktop app.
- Windows / Linux: Rust (`native/system-audio-capture-rs/`). WASAPI loopback or the
  PulseAudio/PipeWire monitor of the default output; no permission prompt.

Where no helper is available the recorder falls back to the loopback-device path.
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from ..config import settings
from ..osinfo import no_window_flags, platform_name

log = logging.getLogger(__name__)

_NATIVE = Path(__file__).resolve().parents[3] / "native"


def _dev_paths() -> list[Path]:
    """Dev build locations: the Swift build on macOS, the cargo build elsewhere."""
    platform = platform_name()
    if platform == "macos":
        return [_NATIVE / "system-audio-capture" / "build" / "system-audio-capture"]
    exe = "system-audio-capture.exe" if platform == "windows" else "system-audio-capture"
    crate = _NATIVE / "system-audio-capture-rs" / "target"
    return [crate / "release" / exe, crate / "debug" / exe]


def _same_file(a: str, b: str) -> bool:
    """Path equality as the OS sees it (case-insensitive on Windows)."""
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def sidecar_path() -> str | None:
    """The helper binary path: explicit config/env first, then a dev build."""
    if settings.system_audio_sidecar and Path(settings.system_audio_sidecar).exists():
        return settings.system_audio_sidecar
    for p in _dev_paths():
        if p.exists():
            return str(p)
    return None


def probe_reason(platform: str, exit_code: int | None, stderr: str) -> str:
    """User-facing reason why native capture can't run, from the probe's result.

    `exit_code` None means there is no helper in this build. Exit codes follow the helper
    contract: 2 capture failed · 3 permission denied/unavailable · 4 no device/server."""
    detail = stderr.strip().splitlines()[-1] if stderr.strip() else ""
    if exit_code is None:
        if platform == "macos":
            return ("Native system-audio capture needs the Sirina desktop app. "
                    "Pick a loopback device (e.g. BlackHole) instead.")
        return ("Native system-audio capture needs the Sirina desktop app. "
                "Pick a loopback input device instead.")
    if platform == "macos":
        if exit_code == 3:
            return ("Grant Screen Recording permission (System Settings → Privacy & Security → "
                    "Screen Recording), or pick a loopback device (e.g. BlackHole) instead.")
        if exit_code == 4:
            return "No display is available for system-audio capture."
    elif platform == "windows":
        if exit_code == 4:
            return "No audio output device was found. Connect or enable speakers or headphones."
    else:
        if exit_code == 4:
            return ("No PulseAudio or PipeWire sound server was found. Install pipewire-pulse "
                    "or pulseaudio, or pick a loopback input device instead.")
    suffix = f" ({detail})" if detail else ""
    return f"System-audio capture couldn't start{suffix}."


def native_available() -> tuple[bool, str | None]:
    """(True, None) if the helper exists and `--probe` exits 0, else (False, reason).

    Not cached: on macOS the Screen Recording permission can change at runtime, and audio
    devices come and go; the probe is cheap (it exits right away)."""
    platform = platform_name()
    path = sidecar_path()
    if not path:
        return False, probe_reason(platform, None, "")
    try:
        result = subprocess.run(
            [path, "--probe"], capture_output=True, timeout=10, creationflags=no_window_flags()
        )
    except Exception as e:
        log.warning("native capture probe failed to run (path=%s)", path, exc_info=True)
        return False, probe_reason(platform, 2, str(e))
    if result.returncode != 0:
        err = result.stderr.decode(errors="replace")
        log.info("native system-audio capture unavailable (exit %d): %s", result.returncode, err.strip())
        return False, probe_reason(platform, result.returncode, err)
    return True, None


def exclude_pid() -> int:
    """The process whose audio the helper leaves out: the desktop app (it plays the
    recordings back), else this backend (dev mode, where nothing of ours plays audio)."""
    raw = os.environ.get("SIRINA_APP_PID", "")
    return int(raw) if raw.isdigit() else os.getpid()


def spawn() -> subprocess.Popen:
    """Start the helper; its stdout yields raw 48 kHz mono s16le PCM."""
    path = sidecar_path()
    if not path:
        raise RuntimeError("native system-audio helper not found")
    args = [path]
    if platform_name() != "macos":  # the Swift helper excludes its own process by itself
        args += ["--exclude-pid", str(exclude_pid())]
    return subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0, creationflags=no_window_flags()
    )


def kill_stale() -> None:
    """Best-effort: terminate orphaned helpers left by a prior crash. Safe to call at
    startup (no recording is active yet). Only processes running our exact helper binary
    are touched, never unrelated processes with a similar name."""
    path = sidecar_path()
    if not path:
        return
    try:
        import psutil

        for proc in psutil.process_iter(["exe"]):
            exe = proc.info.get("exe")
            if not exe or not _same_file(exe, path) or proc.pid == os.getpid():
                continue
            log.info("terminating orphaned system-audio helper (pid %d)", proc.pid)
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except psutil.TimeoutExpired:
                proc.kill()
            except psutil.Error:
                pass
    except Exception:
        log.debug("kill_stale failed", exc_info=True)
