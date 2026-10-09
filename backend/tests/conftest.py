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


def exec_wrapper(folder, name: str, script: str) -> str:
    """An executable that runs `script` with this Python, passing its arguments through:
    a shell script on POSIX, a .cmd file on Windows (both run directly by Popen)."""
    import os
    import sys
    from pathlib import Path

    if os.name == "nt":
        path = Path(folder) / f"{name}.cmd"
        path.write_text(f'@"{sys.executable}" "{script}" %*\r\n')
    else:
        path = Path(folder) / name
        path.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
        path.chmod(0o755)
    return str(path)
