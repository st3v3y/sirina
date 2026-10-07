"""Live caption stream: feeds never block, times map onto the recording, failures are contained."""
import sys
import time
from pathlib import Path

import pytest

from app.recording import captions as cap_mod
from app.recording.captions import CaptionStream

FAKE = str(Path(__file__).parent / "fixtures" / "fake_captions.py")


@pytest.fixture()
def helper(tmp_path):
    w = tmp_path / "speech-engine"
    w.write_text(f"#!/bin/sh\nshift\nexec {sys.executable} {FAKE}\n")  # drop the 'captions' arg
    w.chmod(0o755)
    return str(w)


def test_settled_captions_with_offset(helper):
    cs = CaptionStream(helper, offset_s=60.0)
    for _ in range(150):  # 3 s of 20 ms blocks
        cs.feed(b"\x00\x00" * 960)
    lines = cs.stop()
    assert [ln[2] for ln in lines] == ["second 0", "second 1", "second 2"]
    assert lines[0][:2] == (60.0, 61.0)  # started mid-recording → recording time


def test_full_queue_drops_instead_of_blocking(helper, monkeypatch):
    monkeypatch.setattr(cap_mod, "QUEUE_BLOCKS", 2)
    cs = CaptionStream(helper)
    t0 = time.monotonic()
    for _ in range(5000):
        cs.feed(b"\x00\x00" * 960)
    assert time.monotonic() - t0 < 1.0  # the capture thread never waited
    cs.stop()


def test_helper_crash_marks_failed_and_feed_is_noop(helper, monkeypatch):
    monkeypatch.setenv("FAKE_CAPTIONS_CRASH", "1")
    cs = CaptionStream(helper)
    for _ in range(50):
        cs.feed(b"\x00\x00" * 960)
        time.sleep(0.005)
    assert cs.stop() == []
    assert cs.snapshot()["failed"] is True
