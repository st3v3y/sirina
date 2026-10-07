"""Best-effort idle-sleep prevention for the duration of a recording.

On macOS we hold an IOKit power assertion (`PreventUserIdleSystemSleep`) so the machine
can't idle-sleep mid-recording and silently cut capture. This is a thin ctypes shim — no
new dependency — and a no-op on other platforms or if IOKit can't be loaded.
"""
from __future__ import annotations

import ctypes
import logging
import sys
import threading

log = logging.getLogger(__name__)

# IOPMAssertionCreateWithName constants.
_kIOPMAssertionLevelOn = 255
_kCFStringEncodingUTF8 = 0x08000100


class SleepBlocker:
    """Holds an idle-sleep assertion until released. Safe to acquire/release repeatedly."""

    def __init__(self) -> None:
        self._assertion_id: ctypes.c_uint32 | None = None
        self._iokit = None

    def acquire(self, reason: str = "Sirina is recording") -> None:
        if self._assertion_id is not None or sys.platform != "darwin":
            return
        try:
            iokit = ctypes.cdll.LoadLibrary(
                "/System/Library/Frameworks/IOKit.framework/IOKit"
            )
            cf = ctypes.cdll.LoadLibrary(
                "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
            )
            cf.CFStringCreateWithCString.restype = ctypes.c_void_p
            cf.CFStringCreateWithCString.argtypes = [
                ctypes.c_void_p,
                ctypes.c_char_p,
                ctypes.c_uint32,
            ]

            def cfstr(s: str) -> ctypes.c_void_p:
                return cf.CFStringCreateWithCString(
                    None, s.encode("utf-8"), _kCFStringEncodingUTF8
                )

            iokit.IOPMAssertionCreateWithName.restype = ctypes.c_int
            iokit.IOPMAssertionCreateWithName.argtypes = [
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_uint32),
            ]
            assertion_id = ctypes.c_uint32(0)
            rv = iokit.IOPMAssertionCreateWithName(
                cfstr("PreventUserIdleSystemSleep"),
                _kIOPMAssertionLevelOn,
                cfstr(reason),
                ctypes.byref(assertion_id),
            )
            if rv != 0:
                log.warning("could not create idle-sleep assertion (IOReturn=%d)", rv)
                return
            self._iokit = iokit
            self._assertion_id = assertion_id
            log.info("idle-sleep prevented for the recording")
        except Exception:
            log.warning("idle-sleep prevention unavailable", exc_info=True)

    def release(self) -> None:
        if self._assertion_id is None or self._iokit is None:
            return
        try:
            self._iokit.IOPMAssertionRelease.argtypes = [ctypes.c_uint32]
            self._iokit.IOPMAssertionRelease(self._assertion_id)
        except Exception:
            log.debug("idle-sleep assertion release failed", exc_info=True)
        finally:
            self._assertion_id = None
            self._iokit = None


class PowerGuard:
    """Process-wide idle-sleep guard shared by recordings and processing jobs.

    Each holder is a key (e.g. ``("recording", 7)`` or ``("job", 7)``); the IOKit assertion
    is held while at least one key is held. Keys make hold/release idempotent, so a job
    released twice (or a recording stopped after a crash path) can't underflow the count.
    Holding across the recording → processing handoff keeps a laptop from idle-sleeping
    mid-transcription once the recording itself has stopped."""

    def __init__(self, blocker: SleepBlocker | None = None) -> None:
        self._blocker = blocker or SleepBlocker()
        self._holders: set[tuple[str, int]] = set()
        self._lock = threading.Lock()

    def hold(self, key: tuple[str, int], reason: str = "Sirina is recording or transcribing") -> None:
        with self._lock:
            first = not self._holders
            self._holders.add(key)
            if first:
                self._blocker.acquire(reason)

    def release(self, key: tuple[str, int]) -> None:
        with self._lock:
            if key not in self._holders:
                return
            self._holders.discard(key)
            if not self._holders:
                self._blocker.release()

    def holders(self) -> set[tuple[str, int]]:
        with self._lock:
            return set(self._holders)


power_guard = PowerGuard()


_POWER_TTL_S = 30.0
_power_cache: tuple[float, dict] | None = None


def _pmset(*args: str) -> str:
    import subprocess

    return subprocess.run(["pmset", *args], capture_output=True, text=True, timeout=5).stdout


def parse_power_state(batt: str, settings_out: str) -> dict:
    """Pure parser for `pmset -g batt` and `pmset -g` output → {on_battery, low_power}.
    `pmset -g` lists the settings of the active power source, so its `lowpowermode`
    line is the mode in effect right now."""
    on_battery = "'Battery Power'" in batt
    low_power = False
    for line in settings_out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "lowpowermode":
            low_power = parts[1] == "1"
    return {"on_battery": on_battery, "low_power": low_power}


def power_state(now: float | None = None) -> dict:
    """Current power source and Low Power Mode (macOS), cached for 30 s; all False
    elsewhere or when pmset is unavailable."""
    import time

    global _power_cache
    now = time.monotonic() if now is None else now
    if _power_cache is not None and now - _power_cache[0] < _POWER_TTL_S:
        return _power_cache[1]
    state = {"on_battery": False, "low_power": False}
    if sys.platform == "darwin":
        try:
            state = parse_power_state(_pmset("-g", "batt"), _pmset("-g"))
        except Exception:
            log.debug("pmset unavailable", exc_info=True)
    _power_cache = (now, state)
    return state


def power_note(state: dict) -> str | None:
    """User-facing explanation when the power state slows transcription, else None."""
    if state.get("low_power"):
        return "Low Power Mode is on, so transcription runs much slower. Plug in or turn it off to speed it up."
    if state.get("on_battery"):
        return "Running on battery. Transcription may be slower than when plugged in."
    return None
