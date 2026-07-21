"""Post-processing audio compression: WAV → AAC (.m4a) via macOS's built-in
`afconvert` (no extra dependency). A finished recording's PCM WAVs are ~10-15×
larger than 64 kbps AAC, so tracks are converted as the final stage of processing
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
import shutil
import subprocess
from pathlib import Path

from sqlmodel import Session

from ..config import settings
from ..db import engine
from ..models import Recording

log = logging.getLogger(__name__)

_TRACK_ATTRS = ("mic_path", "system_path", "audio_path")


def available() -> bool:
    return shutil.which("afconvert") is not None


def _afconvert(args: list[str]) -> None:
    proc = subprocess.run(
        ["afconvert", *args], capture_output=True, text=True, timeout=1800
    )
    if proc.returncode != 0:
        raise RuntimeError(f"afconvert failed: {(proc.stderr or proc.stdout).strip()[:300]}")


def encode_wav(wav: Path) -> Path:
    """WAV → AAC in an .m4a container (64 kbps, fine for speech). Raises on failure."""
    out = wav.with_suffix(".m4a")
    try:
        _afconvert(["-f", "m4af", "-d", "aac", "-b", "65536", str(wav), str(out)])
    except RuntimeError:
        # 64 kbps is outside the codec's allowed range for some sample rates
        # (e.g. 16 kHz mono) — retry letting the codec pick its default bitrate.
        _afconvert(["-f", "m4af", "-d", "aac", str(wav), str(out)])
    if not out.exists() or out.stat().st_size == 0:
        out.unlink(missing_ok=True)
        raise RuntimeError(f"afconvert produced no output for {wav.name}")
    return out


def decode_m4a(m4a: Path) -> Path:
    """AAC .m4a → 16-bit PCM WAV (source sample rate/channels kept). Raises on failure."""
    out = m4a.with_suffix(".wav")
    _afconvert(["-f", "WAVE", "-d", "LEI16", str(m4a), str(out)])
    if not out.exists() or out.stat().st_size == 0:
        out.unlink(missing_ok=True)
        raise RuntimeError(f"afconvert produced no output for {m4a.name}")
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
