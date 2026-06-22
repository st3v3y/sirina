"""Audio input device discovery (PortAudio via sounddevice).

Capture itself lives in app/recording/recorder.py; this module only resolves and
lists input devices.
"""
from __future__ import annotations

import logging

import sounddevice as sd

log = logging.getLogger(__name__)


def refresh_devices() -> None:
    """Re-enumerate audio devices. PortAudio caches the device list at initialization, so
    a device connected after startup (e.g. Bluetooth headphones) won't appear until
    PortAudio is reinitialized. MUST NOT be called while a stream is open — it tears down
    the PortAudio instance — so callers guard on there being no active recording."""
    try:
        sd._terminate()
        sd._initialize()
    except Exception:
        log.warning("portaudio re-enumeration failed", exc_info=True)


def list_input_devices(refresh: bool = False) -> list[dict]:
    """Return all input-capable audio devices. With refresh=True, re-enumerate first so a
    newly connected device shows up."""
    if refresh:
        refresh_devices()
    devices = sd.query_devices()
    out: list[dict] = []
    for i, d in enumerate(devices):
        if int(d.get("max_input_channels", 0) or 0) <= 0:
            continue
        out.append(
            {
                "index": i,
                "name": d["name"],
                "channels": int(d["max_input_channels"]),
                "default_samplerate": float(d.get("default_samplerate") or 48000),
            }
        )
    return out


def find_device(spec: str | int | None) -> int | None:
    """Resolve a device by index, name substring, or None (system default)."""
    if spec is None:
        return None
    if isinstance(spec, int):
        return spec
    spec_norm = spec.strip().lower()
    for i, d in enumerate(sd.query_devices()):
        if int(d.get("max_input_channels", 0) or 0) <= 0:
            continue
        if d["name"].strip().lower() == spec_norm or spec_norm in d["name"].lower():
            return i
    raise ValueError(f"no input device matching {spec!r}")
