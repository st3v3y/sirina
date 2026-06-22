"""Best-effort idle-sleep prevention for the duration of a recording.

On macOS we hold an IOKit power assertion (`PreventUserIdleSystemSleep`) so the machine
can't idle-sleep mid-recording and silently cut capture. This is a thin ctypes shim — no
new dependency — and a no-op on other platforms or if IOKit can't be loaded.
"""
from __future__ import annotations

import ctypes
import logging
import sys

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
