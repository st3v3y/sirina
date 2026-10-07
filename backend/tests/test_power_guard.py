"""PowerGuard: one idle-sleep assertion shared by recordings and jobs, keyed holders."""
from app.audio.power import PowerGuard


class FakeBlocker:
    def __init__(self) -> None:
        self.acquired = 0
        self.released = 0

    def acquire(self, reason: str = "") -> None:
        self.acquired += 1

    def release(self) -> None:
        self.released += 1


def test_assertion_spans_recording_to_job_handoff():
    b = FakeBlocker()
    g = PowerGuard(b)
    g.hold(("recording", 7))
    g.hold(("job", 7))  # enqueued before the recorder lets go
    g.release(("recording", 7))
    assert (b.acquired, b.released) == (1, 0)  # no gap: still held by the job
    g.release(("job", 7))
    assert (b.acquired, b.released) == (1, 1)


def test_release_is_idempotent_and_unknown_keys_are_ignored():
    b = FakeBlocker()
    g = PowerGuard(b)
    g.hold(("job", 1))
    g.release(("job", 1))
    g.release(("job", 1))
    g.release(("recording", 9))
    assert (b.acquired, b.released) == (1, 1)
    assert g.holders() == set()


def test_repeated_hold_of_same_key_counts_once():
    b = FakeBlocker()
    g = PowerGuard(b)
    g.hold(("job", 2))
    g.hold(("job", 2))
    g.release(("job", 2))
    assert (b.acquired, b.released) == (1, 1)
