"""The platform the backend runs on, and small cross-platform process helpers."""
from __future__ import annotations

import os
import subprocess
import sys

PLATFORM_LABELS = {"macos": "macOS", "windows": "Windows", "linux": "Linux"}


def platform_name() -> str:
    """`macos`, `windows` or `linux` (any other Unix counts as linux)."""
    if sys.platform == "darwin":
        return "macos"
    if os.name == "nt":
        return "windows"
    return "linux"


def platform_label() -> str:
    return PLATFORM_LABELS[platform_name()]


def no_window_flags() -> int:
    """`creationflags` that keep a child process from opening a console on Windows."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
