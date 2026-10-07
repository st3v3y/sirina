"""Shared test setup."""
import pytest


class _NoopBlocker:
    def acquire(self, reason: str = "") -> None:
        pass

    def release(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _no_real_sleep_assertion(monkeypatch):
    """Never create a real IOKit idle-sleep assertion from tests (jobs and recordings
    hold the shared power guard)."""
    from app.audio import power

    monkeypatch.setattr(power.power_guard, "_blocker", _NoopBlocker())
    monkeypatch.setattr(power.power_guard, "_holders", set())
