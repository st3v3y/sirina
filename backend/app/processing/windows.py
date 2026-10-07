"""Window-by-window finalization of a recording's transcript.

Both the post-stop job and transcription during recording call `finalize_range`; neither
has its own loop. A window is cut at a silence (ideally one shared by all tracks), every
non-silent track is transcribed for that window, and the result is committed in one
transaction that replaces the window's draft lines with final ones and advances the
recording's stored `final_until_s`. Cutting at silences keeps quality unchanged: the
engines already decode ~30 s VAD chunks independently.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlmodel import Session, delete, select

from ..models import Recording, Segment, Speaker
from ..speakers import SELF_LABEL, get_or_create_self_person
from ..transcribe.whisper import TLine
from .segment import resegment_lines

log = logging.getLogger(__name__)

Region = tuple[float, float]

MIN_GAP_S = 0.5  # a cut needs at least this much silence
SEARCH_S = 30.0  # look this far around each target for a silence
VAD_CHUNK_S = 600.0  # run VAD over long tracks in slices to bound memory


@dataclass(frozen=True)
class Track:
    name: str  # "mic" | "system" | "single"
    label: str  # speaker label: "You" | "Speaker 1"
    color: str
    path: str


def tracks_for(mic_path: str | None, system_path: str | None, audio_path: str | None, colors) -> list[Track]:
    """The tracks a recording is transcribed as — shared by the job and transcription
    during recording, so both write to the same speaker rows. Two tracks: mic = "You",
    system = "Speaker 1". Otherwise the single track is "Speaker 1". (Silence filtering is
    the caller's business.)"""
    if mic_path and system_path:
        return [Track("mic", "You", colors(0), mic_path), Track("system", "Speaker 1", colors(1), system_path)]
    path = audio_path or mic_path or system_path
    return [Track("single", "Speaker 1", colors(0), path)] if path else []


# ---------------------------------------------------------------- speech regions (IO)


def speech_regions(path: str, start_s: float = 0.0, end_s: float | None = None) -> list[Region]:
    """Speech regions of a WAV between start_s and end_s (absolute seconds), via the
    Silero VAD bundled with faster-whisper. Runs in slices so a 2-hour track never
    has to sit in memory as one array."""
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    from ..audio.wav import TARGET_SR, load_wav_16k, wav_duration_s

    end = wav_duration_s(path) if end_s is None else end_s
    regions: list[Region] = []
    t = start_s
    while t < end:
        stop = min(end, t + VAD_CHUNK_S)
        audio = load_wav_16k(path, t, stop)
        if audio.size:
            for r in get_speech_timestamps(audio, VadOptions()):
                regions.append((t + r["start"] / TARGET_SR, t + r["end"] / TARGET_SR))
        t = stop
    return merge_regions(regions)


# ---------------------------------------------------------------- pure cut logic


def merge_regions(regions: list[Region], join_gap: float = 0.0) -> list[Region]:
    out: list[Region] = []
    for s, e in sorted(regions):
        if out and s <= out[-1][1] + join_gap:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def silences(speech: list[Region], from_s: float, to_s: float) -> list[Region]:
    """Gaps between speech regions inside [from_s, to_s]."""
    gaps: list[Region] = []
    t = from_s
    for s, e in merge_regions(speech):
        if e <= from_s or s >= to_s:
            continue
        if s > t:
            gaps.append((t, min(s, to_s)))
        t = max(t, e)
    if t < to_s:
        gaps.append((t, to_s))
    return gaps


def _intersect(a: list[Region], b: list[Region]) -> list[Region]:
    out: list[Region] = []
    i = j = 0
    while i < len(a) and j < len(b):
        s, e = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if e > s:
            out.append((s, e))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return out


def choose_cuts(
    speech_by_track: list[list[Region]],
    from_s: float,
    to_s: float,
    target_s: float,
    *,
    min_gap: float = MIN_GAP_S,
    search: float = SEARCH_S,
) -> list[float]:
    """Window end points (ascending, last == to_s) near multiples of `target_s`.

    Each cut is the middle of the silence closest to the target that is silent in ALL
    tracks; failing that, silent in ANY track; failing that, the target itself."""
    # Cut only while more than 1.5 windows remain, so the last window is never a tiny
    # tail (>= target/2 - search): very short windows decode worse.
    if target_s <= 0 or to_s - from_s <= target_s * 1.5:
        return [to_s]
    per_track = [[g for g in silences(sp, from_s, to_s) if g[1] - g[0] >= min_gap] for sp in speech_by_track]
    common = per_track[0]
    for gaps in per_track[1:]:
        common = [g for g in _intersect(common, gaps) if g[1] - g[0] >= min_gap]
    any_gap = sorted(g for gaps in per_track for g in gaps)

    cuts: list[float] = []
    prev = from_s
    target = from_s + target_s
    while to_s - prev > target_s * 1.5:
        def best(gaps: list[Region]) -> float | None:
            mids = [(g[0] + g[1]) / 2 for g in gaps]
            mids = [m for m in mids if abs(m - target) <= search and m > prev + min_gap]
            return min(mids, key=lambda m: abs(m - target)) if mids else None

        cut = best(common)
        if cut is None:
            cut = best(any_gap)
        if cut is None:
            cut = target
        cuts.append(cut)
        prev = cut
        target = cut + target_s
    cuts.append(to_s)
    return cuts


def has_speech(speech: list[Region], a: float, b: float) -> bool:
    return any(s < b and e > a for s, e in speech)


# ---------------------------------------------------------------- DB


def _speaker_id(s: Session, recording_id: int, track: Track) -> int:
    """The track's speaker row, created on first use (a silent track gets none)."""
    sp = s.exec(
        select(Speaker).where(Speaker.recording_id == recording_id, Speaker.label == track.label)
    ).first()
    if sp is None:
        sp = Speaker(recording_id=recording_id, label=track.label, color=track.color)
        if track.label == SELF_LABEL:
            sp.person_id = get_or_create_self_person(s).id
        s.add(sp)
        s.flush()
    assert sp.id is not None
    return sp.id


def commit_window(
    db_engine,
    recording_id: int,
    win_start: float,
    win_end: float,
    lines_by_track: list[tuple[Track, list[TLine]]],
    language: str | None,
) -> int:
    """Atomically replace the window's draft lines with final ones and advance
    `final_until_s`. Returns the number of final segments written."""
    written = 0
    with Session(db_engine) as s:
        s.exec(
            delete(Segment).where(  # type: ignore[arg-type]
                Segment.recording_id == recording_id,
                Segment.is_draft == True,  # noqa: E712
                Segment.start_ts < win_end,
                Segment.start_ts >= win_start,
            )
        )
        for track, lines in lines_by_track:
            pieces = resegment_lines(lines)
            if not pieces:
                continue
            speaker_id = _speaker_id(s, recording_id, track)
            for ln in pieces:
                s.add(Segment(
                    recording_id=recording_id,
                    speaker_id=speaker_id,
                    start_ts=ln.start,
                    end_ts=ln.end,
                    text=ln.text,
                    is_draft=False,
                    words=json.dumps([[round(w0, 3), round(w1, 3), t] for (w0, w1, t) in ln.words]) if ln.words else None,
                ))
                written += 1
        rec = s.get(Recording, recording_id)
        if rec is not None:
            rec.final_until_s = win_end
            if language:
                rec.language = language
            s.add(rec)
        s.commit()
    return written


def insert_drafts(db_engine, recording_id: int, lines_by_track: list[tuple[Track, list[TLine]]], after_s: float) -> int:
    """Store draft lines (no words) that start at/after `after_s`, i.e. not yet final."""
    written = 0
    with Session(db_engine) as s:
        for track, lines in lines_by_track:
            keep = [ln for ln in lines if ln.start >= after_s and ln.text.strip()]
            if not keep:
                continue
            speaker_id = _speaker_id(s, recording_id, track)
            for ln in keep:
                s.add(Segment(recording_id=recording_id, speaker_id=speaker_id, start_ts=ln.start,
                              end_ts=ln.end, text=ln.text.strip(), is_draft=True))
                written += 1
        s.commit()
    return written


def final_lines_by_label(db_engine, recording_id: int) -> dict[str, list[TLine]]:
    """Rebuild each speaker's final lines (with stored word timings) for diarization."""
    out: dict[str, list[TLine]] = {}
    with Session(db_engine) as s:
        rows = s.exec(
            select(Segment, Speaker)
            .where(Segment.recording_id == recording_id, Segment.is_draft == False)  # noqa: E712
            .join(Speaker, Segment.speaker_id == Speaker.id)  # type: ignore[arg-type]
            .order_by(Segment.start_ts)
        ).all()
        for seg, sp in rows:
            words = [(float(w[0]), float(w[1]), str(w[2])) for w in json.loads(seg.words)] if seg.words else []
            out.setdefault(sp.label, []).append(TLine(seg.start_ts, seg.end_ts, seg.text, words))
    return out


# ---------------------------------------------------------------- the loop


SpeechFn = Callable[[str, float, float], list[Region]]


async def finalize_range(
    *,
    db_engine,
    recording_id: int,
    tracks: list[Track],
    from_s: float,
    to_s: float,
    target_s: float,
    transcribe: Callable[..., Awaitable[tuple[list[TLine], str | None]]],
    language: str | None,
    should_stop: Callable[[], bool] = lambda: False,
    on_window: Callable[[float], None] | None = None,
    speech_fn: SpeechFn | None = None,
    include_tail: bool = True,
    commit: Callable[..., int] | None = None,
) -> tuple[str | None, int]:
    """Finalize [from_s, to_s) window by window. Returns (language, segments written).

    `transcribe(path, start_s, end_s, language=...)` is the engine's `transcribe_window`.
    Stops between windows when `should_stop()`; what was committed stays final. With
    `include_tail=False` (transcription during recording, where `to_s` is just "audio so
    far") only complete windows are committed and the open tail is left for later.
    `commit` replaces `commit_window` (the live finalizer guards it with its stop lock)."""
    import asyncio

    if to_s <= from_s or not tracks:
        return language, 0
    sf = speech_fn or speech_regions
    speech = [await asyncio.to_thread(sf, t.path, from_s, to_s) for t in tracks]
    cuts = choose_cuts(speech, from_s, to_s, target_s)
    if not include_tail:
        cuts = cuts[:-1]
    written = 0
    a = from_s
    for b in cuts:
        if should_stop():
            break
        lines_by_track: list[tuple[Track, list[TLine]]] = []
        for track, sp in zip(tracks, speech):
            if not has_speech(sp, a, b):
                continue
            lines, detected = await transcribe(track.path, a, b, language=language)
            language = language or detected
            lines_by_track.append((track, lines))
        written += await asyncio.to_thread(commit or commit_window, db_engine, recording_id, a, b, lines_by_track, language)
        if on_window:
            on_window(b)
        a = b
    return language, written
