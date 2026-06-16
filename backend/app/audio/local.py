"""Local audio capture via PortAudio (sounddevice). Mirrors PerUserPCMSink's
contract so the chunker doesn't care where audio comes from."""
from __future__ import annotations

import asyncio
import logging
from math import gcd
from typing import Callable

import numpy as np
import sounddevice as sd
from scipy.signal import resample_poly

log = logging.getLogger(__name__)

TARGET_SR = 16_000


def list_input_devices() -> list[dict]:
    """Return all input-capable audio devices."""
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
    """Resolve a device by index, name, or None (system default)."""
    if spec is None:
        return None
    if isinstance(spec, int):
        return spec
    # match by name (case-insensitive substring)
    spec_norm = spec.strip().lower()
    for i, d in enumerate(sd.query_devices()):
        if int(d.get("max_input_channels", 0) or 0) <= 0:
            continue
        if d["name"].strip().lower() == spec_norm or spec_norm in d["name"].lower():
            return i
    raise ValueError(f"no input device matching {spec!r}")


class LocalAudioSource:
    """Opens an input stream on a PortAudio device and pushes 16 kHz mono float32
    samples into a callback. Callback signature matches the Discord sink's:
    `on_audio(user_id, username, samples_16k)`."""

    def __init__(
        self,
        device: str | int | None,
        label: str,
        on_audio: Callable[[str, str, np.ndarray], None],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._device = find_device(device)
        self._label = label or "Room"
        self._on_audio = on_audio
        self._loop = loop
        self._stream: sd.InputStream | None = None
        info = sd.query_devices(self._device, kind="input") if self._device is not None else sd.query_devices(kind="input")
        self._device_sr = int(info["default_samplerate"])
        self._device_name = info["name"]
        self._channels = max(1, min(2, int(info["max_input_channels"])))

    @property
    def device_name(self) -> str:
        return self._device_name

    @property
    def label(self) -> str:
        return self._label

    def start(self) -> None:
        if self._stream is not None:
            return
        # Open at device's native rate; we resample to 16k inside the callback.
        blocksize = max(256, self._device_sr // 50)  # ~20 ms blocks

        def _cb(indata: np.ndarray, frames: int, time_info, status) -> None:  # PortAudio thread
            if status:
                log.debug("portaudio status: %s", status)
            try:
                # Downmix to mono if multichannel
                if indata.ndim == 2 and indata.shape[1] > 1:
                    mono = indata.mean(axis=1)
                else:
                    mono = indata[:, 0] if indata.ndim == 2 else indata
                if self._device_sr != TARGET_SR:
                    g = gcd(self._device_sr, TARGET_SR)
                    samples = resample_poly(mono, TARGET_SR // g, self._device_sr // g).astype(np.float32)
                else:
                    samples = mono.astype(np.float32, copy=False)
                self._loop.call_soon_threadsafe(self._on_audio, "local", self._label, samples)
            except Exception:
                log.exception("local audio callback failed")

        self._stream = sd.InputStream(
            device=self._device,
            samplerate=self._device_sr,
            channels=self._channels,
            dtype="float32",
            blocksize=blocksize,
            callback=_cb,
        )
        self._stream.start()
        log.info(
            "local audio capture started on '%s' (sr=%d, ch=%d, label=%s)",
            self._device_name,
            self._device_sr,
            self._channels,
            self._label,
        )

    def stop(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            log.exception("error closing audio stream")
        finally:
            self._stream = None
            log.info("local audio capture stopped (%s)", self._device_name)
