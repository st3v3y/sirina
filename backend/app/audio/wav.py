"""Read a time slice of a 16-bit PCM WAV as 16 kHz mono float32 (whisper's input).

Reads only the requested frames (seek, not decode-everything), so transcribing a
3-minute window of a 2-hour recording stays cheap, and works on a WAV that is still
being written (the recorder patches the header after every write)."""
from __future__ import annotations

import wave

import numpy as np

TARGET_SR = 16_000


def _lowpass_taps(factor: int, n: int = 63) -> np.ndarray:
    """Windowed-sinc low-pass for decimating by `factor` (cutoff just under the new Nyquist)."""
    cutoff = 0.9 / factor  # fraction of the input Nyquist
    k = np.arange(n) - (n - 1) / 2
    taps = cutoff * np.sinc(cutoff * k) * np.hamming(n)
    return taps / taps.sum()


def resample_to_16k(audio: np.ndarray, sr: int) -> np.ndarray:
    """NumPy-only resampling (scipy isn't in the default app bundle). The recorder writes
    48 kHz, an integer multiple: filter + decimate. Other rates: linear interpolation."""
    if sr == TARGET_SR or audio.size == 0:
        return audio
    if sr % TARGET_SR == 0:
        factor = sr // TARGET_SR
        filtered = np.convolve(audio, _lowpass_taps(factor), mode="same")
        return filtered[::factor]
    n_out = int(round(audio.size * TARGET_SR / sr))
    x_old = np.arange(audio.size) / sr
    x_new = np.arange(n_out) / TARGET_SR
    return np.interp(x_new, x_old, audio)


def wav_duration_s(path: str) -> float:
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate() or 1)


def load_wav_16k(path: str, start_s: float = 0.0, end_s: float | None = None) -> np.ndarray:
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        if w.getsampwidth() != 2:
            raise RuntimeError(f"unsupported {w.getsampwidth() * 8}-bit WAV (expected 16-bit): {path}")
        total = w.getnframes()
        start = max(0, min(total, int(round(start_s * sr))))
        end = total if end_s is None else max(start, min(total, int(round(end_s * sr))))
        w.setpos(start)
        raw = w.readframes(end - start)
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        audio = audio.reshape(-1, ch).mean(axis=1)
    audio = resample_to_16k(audio, int(sr))
    return np.ascontiguousarray(audio, dtype=np.float32)
