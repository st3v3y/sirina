"""Leading/trailing silence detection and WAV trimming.

Used after a recording is stopped to offer trimming away long dead air — the
"forgot to stop the recording" case, where the call (system track) ends but the
mic keeps capturing room noise for minutes or hours. Detecting on the system
track (the actual conversation) is what makes the trailing case work: the mic's
ambient noise floor would otherwise read as "still active" to the very end.

All functions are memory-bounded: WAVs (which can be gigabytes for a multi-hour
recording) are scanned and rewritten in blocks, never loaded whole.
"""
from __future__ import annotations

import logging
import wave
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

# A block is "active" if its peak amplitude reaches this fraction of int16 full-scale.
# Set above a typical room/line noise floor so quiet-but-not-silent stretches (breathing,
# fan hum) don't defeat trailing-silence detection.
ACTIVE_PEAK_THRESHOLD = 0.02
# Granularity of the activity scan. 1 s keeps a single stray click from anchoring the span.
SCAN_WINDOW_S = 1.0


def _wav_frames_rate(path: Path) -> tuple[int, int]:
    with wave.open(str(path), "rb") as w:
        return w.getnframes(), (w.getframerate() or 48_000)


def _active_span(path: Path, threshold: float, window_s: float) -> tuple[float, float] | None:
    """Return (first_active_s, last_active_s) for a mono int16 WAV, or None if the whole
    file is below `threshold`. `last_active_s` is the end of the last active window."""
    try:
        with wave.open(str(path), "rb") as w:
            sr = w.getframerate() or 48_000
            win = max(1, int(sr * window_s))
            pos = 0
            first: float | None = None
            last = 0.0
            while True:
                raw = w.readframes(win)
                if not raw:
                    break
                arr = np.frombuffer(raw, dtype=np.int16)
                if arr.size and (float(np.abs(arr).max()) / 32768.0) >= threshold:
                    if first is None:
                        first = pos / sr
                    last = (pos + arr.size) / sr
                pos += arr.size
    except Exception:
        log.debug("active-span scan failed for %s", path, exc_info=True)
        return None
    if first is None:
        return None
    return first, last


def detect_trim(
    mic_path: Path | None,
    system_path: Path | None,
    *,
    threshold: float = ACTIVE_PEAK_THRESHOLD,
    min_silence_s: float = 60.0,
) -> dict | None:
    """Detect trimmable leading/trailing silence across a recording's tracks.

    Detection keys on the system track when present and non-silent (it tracks the actual
    conversation, so it goes quiet the moment a call ends), otherwise the mic track.
    Returns {"leading_s", "trailing_s", "start_s", "end_s", "duration_s"} when the combined
    silence is at least `min_silence_s` AND some audio would remain, else None.
    """
    tracks = [p for p in (mic_path, system_path) if p and Path(p).exists()]
    if not tracks:
        return None
    def _seconds(p: Path) -> float:
        frames, rate = _wav_frames_rate(p)
        return frames / rate

    total_s = max(_seconds(p) for p in tracks)

    # Prefer the system track for detection; fall back to mic if there's no system track
    # or it's entirely silent (e.g. the far side never came through).
    span: tuple[float, float] | None = None
    if system_path and Path(system_path).exists():
        span = _active_span(Path(system_path), threshold, SCAN_WINDOW_S)
    if span is None and mic_path and Path(mic_path).exists():
        span = _active_span(Path(mic_path), threshold, SCAN_WINDOW_S)
    if span is None:
        return None  # nothing active anywhere — not our job to trim a fully silent take

    start_s, end_s = span
    end_s = min(end_s, total_s)
    leading_s = max(0.0, start_s)
    trailing_s = max(0.0, total_s - end_s)
    if leading_s + trailing_s < min_silence_s:
        return None
    if end_s - start_s <= 0:
        return None  # would trim away everything
    return {
        "leading_s": round(leading_s, 1),
        "trailing_s": round(trailing_s, 1),
        "start_s": start_s,
        "end_s": end_s,
        "duration_s": round(total_s, 1),
    }


def trim_wav_window(src: Path, dst: Path, start_s: float, end_s: float) -> None:
    """Copy the [start_s, end_s] window of a mono int16 WAV `src` to `dst`, block by block.
    The window is clamped to the file's own length. `dst` may equal `src` only via a temp
    file the caller swaps in — this writes a fresh file."""
    with wave.open(str(src), "rb") as w:
        sr = w.getframerate() or 48_000
        nframes = w.getnframes()
        start_f = max(0, min(nframes, int(start_s * sr)))
        end_f = max(start_f, min(nframes, int(end_s * sr)))
        w.setpos(start_f)
        with wave.open(str(dst), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(sr)
            remaining = end_f - start_f
            block = sr * 30  # 30 s blocks → bounded memory
            while remaining > 0:
                chunk = w.readframes(min(block, remaining))
                if not chunk:
                    break
                out.writeframes(chunk)
                remaining -= min(block, remaining)
