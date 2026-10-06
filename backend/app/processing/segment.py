"""Re-segment transcript lines into turn-/sentence-sized pieces.

Whisper (and the diarizer's per-speaker regrouping) can emit a single line spanning
minutes of one speaker. In a two-track recording (You + the far side) each track is
transcribed independently, so those long lines render as two monologues instead of the
real back-and-forth. Splitting long lines at natural pauses and sentence boundaries lets
the two tracks interleave by timestamp into a readable conversation.

Splitting is conservative: normal sentence-sized lines pass through untouched; only long
runs (by duration or a big inter-word pause) are broken up.
"""
from __future__ import annotations

import re

from ..transcribe.whisper import TLine, Word

# A pause at least this long between consecutive words starts a new line (a turn/breath).
PAUSE_GAP_S = 0.8
# A silence this long always splits, even into short slivers: a line spanning it would
# sort ahead of everything the other track said in between.
LONG_GAP_S = 5.0
# Past this duration, split at the next sentence end; past the hard cap, split regardless.
TARGET_DUR_S = 8.0
HARD_DUR_S = 16.0
# Don't emit slivers: a sub-line must have at least this many characters before a split
# (short bits are merged into the neighbouring piece instead).
MIN_CHARS = 40

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")

# Typical speaking rate. A line without word timestamps whose span is far longer than its
# text could take to say (a segment-level time stretched across silence) is clamped to a
# plausible length from its start instead of spreading its sentences over the whole span.
CHARS_PER_S = 15.0
_IMPLAUSIBLE_FACTOR = 3.0


def _ends_sentence(text: str) -> bool:
    return text.rstrip()[-1:] in ".!?…"


def _split_with_words(ln: TLine) -> list[TLine]:
    """Split a line that has word timestamps at big pauses and sentence ends."""
    subs: list[TLine] = []
    cur: list[Word] = []

    def flush() -> None:
        if cur:
            text = " ".join(w[2] for w in cur).strip()
            subs.append(TLine(cur[0][0], cur[-1][1], text, list(cur)))

    for w in ln.words:
        if cur:
            gap = w[0] - cur[-1][1]
            dur = cur[-1][1] - cur[0][0]
            long_enough = sum(len(x[2]) + 1 for x in cur) >= MIN_CHARS
            at_sentence = _ends_sentence(cur[-1][2])
            if (
                gap >= LONG_GAP_S
                or (gap >= PAUSE_GAP_S and long_enough)
                or (dur >= TARGET_DUR_S and at_sentence and long_enough)
                or (dur >= HARD_DUR_S)
            ):
                flush()
                cur = []
        cur.append(w)
    flush()
    return subs or [ln]


def _merge_small(parts: list[str]) -> list[str]:
    """Fold sentence fragments shorter than MIN_CHARS into the previous piece."""
    merged: list[str] = []
    for p in parts:
        if merged and len(p) < MIN_CHARS:
            merged[-1] = f"{merged[-1]} {p}".strip()
        else:
            merged.append(p)
    return merged


def _split_without_words(ln: TLine) -> list[TLine]:
    """Split a line lacking word timestamps at sentence boundaries, distributing the
    line's time span across pieces in proportion to their length (timestamps are display
    anchors, so an approximate split is fine)."""
    text = ln.text.strip()
    dur = ln.end - ln.start
    plausible = len(text) / CHARS_PER_S
    if dur > HARD_DUR_S and dur > _IMPLAUSIBLE_FACTOR * plausible:
        dur = plausible
        ln = TLine(ln.start, round(ln.start + dur, 3), ln.text, [])
    # Leave normal-sized lines alone; only break up clearly long ones.
    if dur <= HARD_DUR_S and len(text) <= 180:
        return [ln]
    parts = _merge_small([p for p in _SENTENCE_SPLIT.split(text) if p.strip()])
    if len(parts) <= 1:
        return [ln]
    total = sum(len(p) for p in parts) or 1
    out: list[TLine] = []
    t = ln.start
    for i, p in enumerate(parts):
        end = ln.end if i == len(parts) - 1 else min(ln.end, t + dur * (len(p) / total))
        out.append(TLine(round(t, 3), round(end, 3), p.strip(), []))
        t = end
    return out


def resegment_lines(lines: list[TLine]) -> list[TLine]:
    """Break long transcript lines into turn-/sentence-sized pieces. Order is preserved."""
    out: list[TLine] = []
    for ln in lines:
        out.extend(_split_with_words(ln) if ln.words else _split_without_words(ln))
    return out
