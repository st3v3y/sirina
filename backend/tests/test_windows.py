"""Window cutting (pure) and the draft→final commit (DB)."""
import asyncio
import json

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Recording, Segment, Speaker
from app.processing import windows as w
from app.transcribe.whisper import TLine


# ---------------------------------------------------------------- choose_cuts


@pytest.mark.parametrize(
    "speech, from_s, to_s, target, expected",
    [
        # Short range → a single window.
        ([[(0, 50)]], 0, 100, 180, [100]),
        # Common silence near 180 s in both tracks → cut in its middle; 220 s left is < 1.5 windows.
        ([[(0, 178), (182, 500)], [(0, 179), (181, 500)]], 0, 400, 180, [180.0, 400]),
        # Common silence beats a closer single-track one.
        ([[(0, 175), (205, 500)], [(0, 178), (182, 500)]], 0, 500, 180, [180.0, 360, 500]),
        # No common silence: mic silent 160–170 (mid 165), system 195–199 (mid 197) → closer wins.
        ([[(0, 160), (170, 400)], [(0, 195), (199, 400)]], 0, 400, 180, [165.0, 400]),
        # Continuous speech in all tracks → cut at the target itself.
        ([[(0, 600)]], 0, 600, 180, [180, 360, 600]),
        # Range starting later (resume): targets count from from_s.
        ([[(100, 278), (282, 500)]], 100, 500, 180, [280.0, 500]),
    ],
)
def test_choose_cuts(speech, from_s, to_s, target, expected):
    assert w.choose_cuts(speech, from_s, to_s, target) == expected


def test_choose_cuts_zero_target_is_one_window():
    assert w.choose_cuts([[(0, 1000)]], 0, 1000, 0) == [1000]


def test_cuts_are_increasing_and_end_at_to_s():
    speech = [[(i * 7.0, i * 7.0 + 6.0) for i in range(200)]]
    cuts = w.choose_cuts(speech, 0, 1400, 180)
    assert cuts == sorted(cuts) and cuts[-1] == 1400 and len(set(cuts)) == len(cuts)


def test_silences_inside_range():
    assert w.silences([(10, 20), (30, 40)], 0, 50) == [(0, 10), (20, 30), (40, 50)]
    assert w.silences([(0, 50)], 0, 50) == []


# ---------------------------------------------------------------- commit / finalize


@pytest.fixture()
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        rec = Recording(status="processing")
        s.add(rec)
        s.commit()
        s.refresh(rec)
        rid = rec.id
    return eng, rid


MIC = w.Track("mic", "You", "sky", "/mic.wav")
SYS = w.Track("system", "Speaker 1", "rose", "/sys.wav")


def _segments(eng, rid):
    with Session(eng) as s:
        return s.exec(select(Segment).where(Segment.recording_id == rid).order_by(Segment.start_ts)).all()


def test_commit_replaces_drafts_in_window_only(db):
    eng, rid = db
    w.insert_drafts(eng, rid, [(MIC, [TLine(5, 6, "draft a"), TLine(200, 201, "draft b")])], after_s=0)
    w.commit_window(eng, rid, 0, 190, [(MIC, [TLine(5, 6, "final a", [(5, 6, "final"), (5.5, 6, "a")])])], "en")
    segs = _segments(eng, rid)
    assert [(s.text, s.is_draft) for s in segs] == [("final a", False), ("draft b", True)]
    assert json.loads(segs[0].words)[0] == [5, 6, "final"]
    with Session(eng) as s:
        rec = s.get(Recording, rid)
        assert rec.final_until_s == 190 and rec.language == "en"


def test_silent_track_gets_no_speaker(db):
    eng, rid = db
    w.commit_window(eng, rid, 0, 100, [(MIC, [TLine(1, 2, "hi")])], None)
    with Session(eng) as s:
        assert [sp.label for sp in s.exec(select(Speaker)).all()] == ["You"]


def test_drafts_before_final_point_are_not_inserted(db):
    eng, rid = db
    n = w.insert_drafts(eng, rid, [(SYS, [TLine(10, 11, "old"), TLine(300, 301, "new")])], after_s=200)
    assert n == 1 and [s.text for s in _segments(eng, rid)] == ["new"]


def test_final_lines_round_trip_words(db):
    eng, rid = db
    w.commit_window(eng, rid, 0, 100, [(SYS, [TLine(1, 3, "a b", [(1, 2, "a"), (2, 3, "b")])])], None)
    lines = w.final_lines_by_label(eng, rid)
    assert lines["Speaker 1"][0].words == [(1.0, 2.0, "a"), (2.0, 3.0, "b")]


def test_finalize_range_both_tracks_per_window_and_stop(db):
    eng, rid = db
    calls = []

    async def transcribe(path, a, b, language=None):
        calls.append((path, a, b))
        return [TLine(a + 1, a + 2, f"{path}@{a:.0f}", [(a + 1, a + 2, "x")])], "en"

    speech = {"/mic.wav": [(0, 600)], "/sys.wav": [(0, 600)]}
    stops = iter([False, False, True])

    async def run():
        return await w.finalize_range(
            db_engine=eng, recording_id=rid, tracks=[MIC, SYS], from_s=0, to_s=600, target_s=180,
            transcribe=transcribe, language=None, should_stop=lambda: next(stops),
            speech_fn=lambda p, a, b: speech[p],
        )

    lang, written = asyncio.run(run())
    assert lang == "en"
    # Two windows ran (stop before the third), each transcribing mic then system.
    assert [c[0] for c in calls] == ["/mic.wav", "/sys.wav", "/mic.wav", "/sys.wav"]
    with Session(eng) as s:
        assert s.get(Recording, rid).final_until_s == 360


def test_rename_during_processing_survives_window_commits(db):
    eng, rid = db
    w.insert_drafts(eng, rid, [(SYS, [TLine(5, 6, "draft"), TLine(300, 301, "later draft")])], after_s=0)
    with Session(eng) as s:
        sp = s.exec(select(Speaker).where(Speaker.recording_id == rid)).one()
        sp.person_id = None
        sp.color = "renamed-marker"  # stands in for a user rename (rename touches this row)
        s.add(sp)
        s.commit()
        speaker_id = sp.id
    w.commit_window(eng, rid, 0, 190, [(SYS, [TLine(5, 6, "final")])], None)
    segs = _segments(eng, rid)
    # Draft and final lines share the one speaker row, so the rename shows on both.
    assert {x.speaker_id for x in segs} == {speaker_id}
    with Session(eng) as s:
        assert len(s.exec(select(Speaker)).all()) == 1
