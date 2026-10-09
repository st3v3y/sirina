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


def test_factory_picks_the_platform_blocker():
    from app.audio import power

    assert isinstance(power.make_sleep_blocker("darwin"), power.SleepBlocker)
    assert isinstance(power.make_sleep_blocker("win32"), power.WindowsSleepBlocker)
    assert isinstance(power.make_sleep_blocker("linux"), power.LinuxSleepBlocker)
    assert isinstance(power.make_sleep_blocker("freebsd14"), power.NoopSleepBlocker)


def test_linux_blocker_without_systemd_inhibit_is_a_noop(monkeypatch):
    from app.audio import power

    monkeypatch.setattr(power.shutil, "which", lambda name: None)
    b = power.LinuxSleepBlocker()
    b.acquire("test")  # must not raise
    assert b._proc is None
    b.release()


def test_linux_blocker_holds_and_releases_inhibitor(monkeypatch):
    import subprocess

    from app.audio import power

    started = []

    class FakePopen:
        def __init__(self, args, **kw):
            started.append(args)
            self.terminated = False
            self.stderr = None
            self.returncode = None

        def wait(self, timeout=None):
            if not self.terminated:
                raise subprocess.TimeoutExpired("systemd-inhibit", timeout)
            return 0

        def terminate(self):
            self.terminated = True

    monkeypatch.setattr(power.shutil, "which", lambda name: "/usr/bin/systemd-inhibit")
    monkeypatch.setattr(power.subprocess, "Popen", FakePopen)
    b = power.LinuxSleepBlocker()
    b.acquire("Sirina is recording")
    proc = b._proc
    assert proc is not None and "--what=idle:sleep" in started[0] and started[0][-2:] == ["sleep", "infinity"]
    b.acquire("again")  # idempotent
    assert len(started) == 1
    b.release()
    assert proc.terminated and b._proc is None


def test_linux_blocker_refused_by_logind(monkeypatch):
    import io

    from app.audio import power

    class RefusedPopen:
        def __init__(self, args, **kw):
            self.stderr = io.BytesIO(b"Failed to inhibit: Access denied")
            self.returncode = 1

        def wait(self, timeout=None):
            return 1

    monkeypatch.setattr(power.shutil, "which", lambda name: "/usr/bin/systemd-inhibit")
    monkeypatch.setattr(power.subprocess, "Popen", RefusedPopen)
    b = power.LinuxSleepBlocker()
    b.acquire("x")
    assert b._proc is None
