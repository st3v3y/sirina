"""Best-effort idle-sleep prevention for the duration of a recording.

The machine must not idle-sleep mid-recording (or mid-transcription) and silently cut
capture. Each platform has its own blocker, picked by `make_sleep_blocker()`:

- macOS: an IOKit power assertion (`PreventUserIdleSystemSleep`) via ctypes.
- Windows: `SetThreadExecutionState`, held by a dedicated thread (the state is per thread).
- Linux: a logind inhibitor, held by a `systemd-inhibit … sleep infinity` child process.

Every blocker degrades to a logged no-op when its mechanism is missing.
"""
from __future__ import annotations

import ctypes
import logging
import shutil
import subprocess
import sys
import threading

log = logging.getLogger(__name__)

# IOPMAssertionCreateWithName constants.
_kIOPMAssertionLevelOn = 255
_kCFStringEncodingUTF8 = 0x08000100


class SleepBlocker:
    """macOS: holds an IOKit idle-sleep assertion until released. Safe to acquire/release
    repeatedly."""

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


class WindowsSleepBlocker:
    """Windows: a dedicated thread sets `ES_CONTINUOUS | ES_SYSTEM_REQUIRED |
    ES_DISPLAY_REQUIRED` and keeps it until released (the flags belong to the thread that
    set them, so it has to stay alive)."""

    _ES_CONTINUOUS = 0x80000000
    _ES_SYSTEM_REQUIRED = 0x00000001
    _ES_DISPLAY_REQUIRED = 0x00000002

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def acquire(self, reason: str = "Sirina is recording") -> None:
        if self._thread is not None:
            return
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._hold, args=(self._stop,), name="sleep-blocker", daemon=True)
        self._thread.start()

    def _hold(self, stop: threading.Event) -> None:
        try:
            set_state = ctypes.windll.kernel32.SetThreadExecutionState  # type: ignore[attr-defined]
            set_state.restype = ctypes.c_uint32
            set_state.argtypes = [ctypes.c_uint32]
            if not set_state(self._ES_CONTINUOUS | self._ES_SYSTEM_REQUIRED | self._ES_DISPLAY_REQUIRED):
                log.warning("SetThreadExecutionState failed; sleep is not prevented")
                return
            log.info("idle-sleep prevented")
            stop.wait()
            set_state(self._ES_CONTINUOUS)
        except Exception:
            log.warning("idle-sleep prevention unavailable", exc_info=True)

    def release(self) -> None:
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join(timeout=2)
        self._thread = None


class LinuxSleepBlocker:
    """Linux: a logind idle/sleep inhibitor, held for as long as the `systemd-inhibit`
    child process runs."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None

    def acquire(self, reason: str = "Sirina is recording") -> None:
        if self._proc is not None:
            return
        exe = shutil.which("systemd-inhibit")
        if not exe:
            log.warning("systemd-inhibit not found; idle sleep can't be prevented")
            return
        try:
            self._proc = subprocess.Popen(
                [exe, "--what=idle:sleep", "--who=Sirina", f"--why={reason}", "--mode=block", "sleep", "infinity"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            try:
                self._proc.wait(timeout=0.3)  # exits right away when logind refuses
            except subprocess.TimeoutExpired:
                if self._proc.stderr:
                    self._proc.stderr.close()  # only needed to explain an early exit
                log.info("idle-sleep prevented")
                return
            err = self._proc.stderr.read().decode(errors="replace").strip() if self._proc.stderr else ""
            log.warning("systemd-inhibit exited (%s); idle sleep can't be prevented", err or self._proc.returncode)
            self._proc = None
        except Exception:
            log.warning("idle-sleep prevention unavailable", exc_info=True)
            self._proc = None

    def release(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.terminate()
            self._proc.wait(timeout=3)
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass
        finally:
            self._proc = None


class NoopSleepBlocker:
    def acquire(self, reason: str = "") -> None:
        log.warning("idle-sleep prevention isn't supported on this platform")

    def release(self) -> None:
        pass


def make_sleep_blocker(platform: str | None = None):
    """The sleep blocker for this platform (`sys.platform` values)."""
    platform = sys.platform if platform is None else platform
    if platform == "darwin":
        return SleepBlocker()
    if platform == "win32":
        return WindowsSleepBlocker()
    if platform.startswith("linux"):
        return LinuxSleepBlocker()
    return NoopSleepBlocker()


class PowerGuard:
    """Process-wide idle-sleep guard shared by recordings and processing jobs.

    Each holder is a key (e.g. ``("recording", 7)`` or ``("job", 7)``); the IOKit assertion
    is held while at least one key is held. Keys make hold/release idempotent, so a job
    released twice (or a recording stopped after a crash path) can't underflow the count.
    Holding across the recording → processing handoff keeps a laptop from idle-sleeping
    mid-transcription once the recording itself has stopped."""

    def __init__(self, blocker: SleepBlocker | None = None) -> None:
        self._blocker = blocker or make_sleep_blocker()
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


def _battery_state() -> dict:
    """Windows/Linux: on battery from psutil (False on desktops without a battery). Low
    Power Mode is a macOS notion, so it is always False here."""
    import psutil

    batt = psutil.sensors_battery()
    on_battery = batt is not None and batt.power_plugged is False
    return {"on_battery": on_battery, "low_power": False}


def power_state(now: float | None = None) -> dict:
    """Current power source and Low Power Mode, cached for 30 s. macOS reads `pmset`
    (which also knows Low Power Mode); elsewhere psutil reports the power source. All
    False when it can't be read."""
    import time

    global _power_cache
    now = time.monotonic() if now is None else now
    if _power_cache is not None and now - _power_cache[0] < _POWER_TTL_S:
        return _power_cache[1]
    state = {"on_battery": False, "low_power": False}
    try:
        if sys.platform == "darwin":
            state = parse_power_state(_pmset("-g", "batt"), _pmset("-g"))
        else:
            state = _battery_state()
    except Exception:
        log.debug("power state unavailable", exc_info=True)
    _power_cache = (now, state)
    return state


def power_note(state: dict) -> str | None:
    """User-facing explanation when the power state slows transcription, else None."""
    if state.get("low_power"):
        return "Low Power Mode is on, so transcription runs much slower. Plug in or turn it off to speed it up."
    if state.get("on_battery"):
        return "Running on battery. Transcription may be slower than when plugged in."
    return None
