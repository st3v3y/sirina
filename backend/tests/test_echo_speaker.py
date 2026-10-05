"""Echo-speaker suppression: a system-track cluster that speaks only while the mic
speaks is the user's own echo in the call audio and must be dropped."""
import pytest

from app.config import settings
from app.processing.job import _is_echo_cluster, _overlap_seconds
from app.transcribe.whisper import TLine


def _lines(intervals):
    return [TLine(s, e, "x") for s, e in intervals]


def test_overlap_seconds_basic():
    a = [(0.0, 2.0), (5.0, 6.0)]
    b = [(1.0, 3.0), (5.5, 8.0)]
    assert _overlap_seconds(a, b) == pytest.approx(1.5)  # 1s + 0.5s
    assert _overlap_seconds(a, []) == 0.0
    assert _overlap_seconds([], b) == 0.0


def test_echo_cluster_dropped(monkeypatch):
    monkeypatch.setattr(settings, "echo_speaker_overlap", 0.75)
    # Mic speech 0-100s; echo fragments land inside it; real track total 1000s.
    mic = _lines([(0, 40), (50, 100)])
    echo = _lines([(5, 10), (55, 60), (90, 95)])
    assert _is_echo_cluster(echo, mic, track_total=1000.0) is True


def test_real_speaker_with_low_overlap_kept(monkeypatch):
    monkeypatch.setattr(settings, "echo_speaker_overlap", 0.75)
    mic = _lines([(0, 40)])
    other = _lines([(45, 60), (70, 90)])  # speaks in the gaps — a real person
    assert _is_echo_cluster(other, mic, track_total=1000.0) is False


def test_large_share_never_treated_as_echo(monkeypatch):
    # A main participant whose speech happens to overlap the mic a lot (crosstalk-heavy
    # call) is protected by the share cap.
    monkeypatch.setattr(settings, "echo_speaker_overlap", 0.75)
    mic = _lines([(0, 500)])
    big = _lines([(0, 400)])  # 100% overlap but 40% of the track
    assert _is_echo_cluster(big, mic, track_total=1000.0) is False


def test_disabled_by_zero(monkeypatch):
    monkeypatch.setattr(settings, "echo_speaker_overlap", 0.0)
    mic = _lines([(0, 100)])
    echo = _lines([(5, 10)])
    assert _is_echo_cluster(echo, mic, track_total=1000.0) is False


def test_stefans_meeting_shape(monkeypatch):
    """Replays the real-world case that motivated this: a ~236s cluster, 98% of it
    coinciding with the user's mic speech, in a ~4800s system track → echo, dropped;
    the two genuine participants (low overlap) are kept."""
    monkeypatch.setattr(settings, "echo_speaker_overlap", 0.75)
    mic = _lines([(i * 100.0, i * 100.0 + 50.0) for i in range(80)])  # ~4000s of talking
    echo = _lines([(i * 400.0 + 10.0, i * 400.0 + 33.6) for i in range(10)])  # inside mic spans
    real = _lines([(i * 100.0 + 55.0, i * 100.0 + 90.0) for i in range(20)])  # in the gaps
    assert _is_echo_cluster(echo, mic, track_total=4800.0) is True
    assert _is_echo_cluster(real, mic, track_total=4800.0) is False
