"""Post-processing audio compression: WAV → AAC (.m4a) via PyAV (FFmpeg's AAC
encoder, bundled with the app on every platform). Earlier macOS builds used
`afconvert`; their .m4a files are standard AAC-in-MP4 and decode the same way.

A finished recording's PCM WAVs are ~10-15× larger than 64 kbps AAC, so tracks are converted as the final stage of processing
(before the recording flips to `ready`) and the WAVs deleted. The transcription/
diarization/trim stack only reads PCM WAV, so re-processing decodes the .m4a
tracks back to WAV first (`restore_wavs`, run by the job itself) and re-compresses
at the end.

Track attributes can alias one file: a mic-only recording stores the SAME path in
`mic_path` and `audio_path`. Conversion therefore works on unique paths and then
remaps every attribute that referenced them.

Ordering is crash-safe: new files are fully written and the DB paths committed
BEFORE the old files are unlinked, so a crash at any point leaves the committed
paths valid (worst case: a leftover original alongside the converted file).
"""
from __future__ import annotations

import logging
import wave
from pathlib import Path

from sqlmodel import Session

from ..config import settings
from ..db import engine
from ..models import Recording

log = logging.getLogger(__name__)

_TRACK_ATTRS = ("mic_path", "system_path", "audio_path")


_BITRATE = 64_000  # plenty for speech


def available() -> bool:
    try:
        import av  # noqa: F401
    except Exception:
        return False
    return True


def _layout(channels: int) -> str:
    return "mono" if channels == 1 else "stereo"


def _encode(wav: Path, out: Path, bit_rate: int | None) -> None:
    import av

    with wave.open(str(wav), "rb") as w:
        rate, channels, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        if width != 2 or channels not in (1, 2):
            raise RuntimeError(f"{wav.name}: unsupported WAV ({width * 8}-bit, {channels} ch)")
        with av.open(str(out), "w", format="ipod") as container:  # ipod = .m4a
            stream = container.add_stream("aac", rate=rate, layout=_layout(channels))
            if bit_rate:
                stream.bit_rate = bit_rate
            resampler = av.AudioResampler(format="fltp", layout=_layout(channels), rate=rate,
                                          frame_size=stream.codec_context.frame_size or 1024)
            pts = 0
            while True:
                raw = w.readframes(rate)  # ~1 s at a time; never the whole track in memory
                if not raw:
                    break
                frame = av.AudioFrame(format="s16", layout=_layout(channels), samples=len(raw) // (2 * channels))
                frame.planes[0].update(raw)
                frame.rate = rate
                frame.pts = pts
                pts += frame.samples
                for f in resampler.resample(frame):
                    container.mux(stream.encode(f))
            for f in resampler.resample(None):
                container.mux(stream.encode(f))
            container.mux(stream.encode(None))


def encode_wav(wav: Path) -> Path:
    """WAV → AAC in an .m4a container (64 kbps, fine for speech). Raises on failure."""
    out = wav.with_suffix(".m4a")
    try:
        _encode(wav, out, _BITRATE)
    except Exception as e:
        # Mirror the old afconvert path: if 64 kbps is rejected for this sample rate,
        # retry letting the encoder pick its default bitrate.
        log.debug("AAC encode at %d bps failed for %s (%s); retrying", _BITRATE, wav.name, e)
        out.unlink(missing_ok=True)
        _encode(wav, out, None)
    if not out.exists() or out.stat().st_size == 0:
        out.unlink(missing_ok=True)
        raise RuntimeError(f"AAC encode produced no output for {wav.name}")
    return out


def decode_m4a(m4a: Path) -> Path:
    """AAC .m4a → 16-bit PCM WAV (source sample rate/channels kept). Raises on failure."""
    import av

    out = m4a.with_suffix(".wav")
    try:
        with av.open(str(m4a)) as container:
            stream = container.streams.audio[0]
            rate = stream.codec_context.sample_rate
            channels = min(stream.codec_context.channels, 2)
            resampler = av.AudioResampler(format="s16", layout=_layout(channels), rate=rate)
            with wave.open(str(out), "wb") as w:
                w.setnchannels(channels)
                w.setsampwidth(2)
                w.setframerate(rate)
                for frame in container.decode(stream):
                    for f in resampler.resample(frame):
                        w.writeframes(bytes(f.planes[0])[: f.samples * 2 * channels])
                for f in resampler.resample(None):
                    w.writeframes(bytes(f.planes[0])[: f.samples * 2 * channels])
    except Exception:
        out.unlink(missing_ok=True)
        raise
    if not out.exists() or out.stat().st_size == 0:
        out.unlink(missing_ok=True)
        raise RuntimeError(f"AAC decode produced no output for {m4a.name}")
    return out


def _convert_tracks(
    recording_id: int,
    db_engine,
    *,
    src_suffix: str,
    convert,
) -> bool:
    """Shared conversion driver: convert every unique on-disk track with suffix
    `src_suffix` via `convert(path) -> new_path`, then remap all aliasing attributes
    and commit BEFORE unlinking the originals. Per-file failures leave that file
    (and its attributes) untouched. Returns True if anything was converted."""
    with Session(db_engine or engine) as s:
        rec = s.get(Recording, recording_id)
        if rec is None:
            return False
        paths = {attr: getattr(rec, attr) for attr in _TRACK_ATTRS}

    converted: dict[str, Path] = {}  # old path -> new path
    for p in dict.fromkeys(v for v in paths.values() if v):  # unique, order-preserving
        src = Path(p)
        if src.suffix.lower() != src_suffix or not src.exists():
            continue
        try:
            converted[p] = convert(src)
        except Exception:
            log.exception("converting %s failed; keeping the original", src.name)
    if not converted:
        return False

    with Session(db_engine or engine) as s:
        rec = s.get(Recording, recording_id)
        if rec is None:  # deleted while we were converting — clean up our outputs
            for out in converted.values():
                out.unlink(missing_ok=True)
            return False
        remapped = False
        for attr in _TRACK_ATTRS:
            current = getattr(rec, attr)
            if current in converted:
                setattr(rec, attr, str(converted[current]))
                remapped = True
            elif current != paths.get(attr):
                # Changed underneath us (shouldn't happen while `processing`) — leave it.
                log.warning("recording %d %s changed during conversion; not remapping", recording_id, attr)
        if remapped:
            s.add(rec)
            s.commit()
    if not remapped:
        for out in converted.values():
            out.unlink(missing_ok=True)
        return False
    # Only after the new paths are durably committed do the originals go away.
    for old in converted:
        Path(old).unlink(missing_ok=True)
    return True


def compress_recording(recording_id: int, db_engine=None) -> bool:
    """Convert a recording's WAV tracks to .m4a and update its paths (see module
    docstring for aliasing + crash-safety). Returns True if anything was converted.
    `db_engine` overrides the app database (tests)."""
    if not settings.compress_audio or not available():
        return False
    changed = _convert_tracks(recording_id, db_engine, src_suffix=".wav", convert=encode_wav)
    if changed:
        log.info("recording %d audio compressed to AAC", recording_id)
    return changed


def restore_wavs(recording_id: int, db_engine=None) -> bool:
    """Decode a recording's compressed (.m4a) tracks back to WAV so it can be
    re-processed. Returns False if any compressed track is missing or fails to
    decode (the caller fails the job with a clear message). `db_engine` overrides
    the app database (tests)."""
    with Session(db_engine or engine) as s:
        rec = s.get(Recording, recording_id)
        if rec is None:
            return False
        todo = {
            p
            for attr in _TRACK_ATTRS
            if (p := getattr(rec, attr)) and Path(p).suffix.lower() == ".m4a"
        }
    if not todo:
        return True
    if not available():
        return False
    missing = [p for p in todo if not Path(p).exists()]
    if missing:
        log.warning("compressed track(s) missing on disk: %s", ", ".join(missing))
        return False
    if not _convert_tracks(recording_id, db_engine, src_suffix=".m4a", convert=decode_m4a):
        return False
    # All-or-nothing for the job's sake: if any track is still compressed (a decode
    # failed), the recording can't be processed — report failure.
    with Session(db_engine or engine) as s:
        rec = s.get(Recording, recording_id)
        if rec is None or any(
            (getattr(rec, a) or "").lower().endswith(".m4a") for a in _TRACK_ATTRS
        ):
            return False
    log.info("recording %d audio restored to WAV for re-processing", recording_id)
    return True
