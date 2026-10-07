"""Live captions for one recording track (opt-in, macOS 26+).

The recorder hands each PCM block it writes to the track's WAV to `CaptionStream.feed`.
A writer thread pipes the blocks into a `speech-engine captions` process (Apple's
on-device SpeechTranscriber: ~2.5% of one CPU core, captions within about a second);
a reader thread collects its caption lines. The capture path never waits: when the
queue is full the block is dropped (captions skip, the recording is untouched), and a
crashed helper just ends captioning.
"""
from __future__ import annotations

import json
import logging
import queue
import subprocess
import threading
import time

log = logging.getLogger(__name__)

QUEUE_BLOCKS = 500  # ~10 s of 20 ms blocks; beyond that the helper is clearly behind
KEEP_SETTLED = 400  # settled lines kept in memory (all are persisted as drafts at stop)


class CaptionStream:
    def __init__(self, helper_path: str, *, offset_s: float = 0.0, language: str | None = None,
                 prompt: str | None = None, sample_rate: int = 48000) -> None:
        # Captions started mid-recording count from their first sample; `offset_s` maps
        # that back onto the recording timeline.
        self.offset_s = offset_s
        self.dropped_blocks = 0
        self.failed = False
        self._settled: list[tuple[float, float, str]] = []  # recent, for the screen
        self._all_settled: list[tuple[float, float, str]] = []  # everything, for the draft
        self._provisional: tuple[float, float, str] | None = None
        self._lock = threading.Lock()
        self._queue: queue.Queue[bytes | None] = queue.Queue(maxsize=QUEUE_BLOCKS)
        args = [helper_path, "captions", "--sample-rate", str(sample_rate)]
        if language:
            args += ["--language", language]
        if prompt:
            args += ["--prompt", prompt]
        self._proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._writer = threading.Thread(target=self._write_loop, name="captions-writer", daemon=True)
        self._reader = threading.Thread(target=self._read_loop, name="captions-reader", daemon=True)
        self._writer.start()
        self._reader.start()
        threading.Thread(target=self._drain_stderr, name="captions-stderr", daemon=True).start()

    # -- capture side (PortAudio / sidecar threads): never blocks
    def feed(self, pcm: bytes) -> None:
        if self.failed:
            return
        try:
            self._queue.put_nowait(pcm)
        except queue.Full:
            self.dropped_blocks += 1

    def _write_loop(self) -> None:
        assert self._proc.stdin is not None
        while True:
            block = self._queue.get()
            if block is None:
                break
            try:
                self._proc.stdin.write(block)
            except (BrokenPipeError, OSError, ValueError):
                self.failed = True
                break
        try:
            self._proc.stdin.close()  # EOF → the helper settles its last captions
        except Exception:
            pass

    def _read_loop(self) -> None:
        assert self._proc.stdout is not None
        for raw in self._proc.stdout:
            try:
                c = json.loads(raw)
                item = (float(c["start"]) + self.offset_s, float(c["end"]) + self.offset_s, str(c["text"]))
            except (ValueError, KeyError, TypeError):
                continue
            with self._lock:
                if c.get("kind") == "settled":
                    self._settled.append(item)
                    del self._settled[:-KEEP_SETTLED]
                    self._all_settled.append(item)
                    self._provisional = None
                else:
                    self._provisional = item
        if self._proc.wait() not in (0, None):
            self.failed = True

    def _drain_stderr(self) -> None:
        assert self._proc.stderr is not None
        for line in self._proc.stderr:
            log.info("captions: %s", line.decode(errors="replace").rstrip())

    # -- readers
    def snapshot(self, last: int = 6) -> dict:
        with self._lock:
            return {
                "settled": [{"start": s, "end": e, "text": t} for s, e, t in self._settled[-last:]],
                "provisional": (
                    {"start": self._provisional[0], "end": self._provisional[1], "text": self._provisional[2]}
                    if self._provisional else None
                ),
                "failed": self.failed,
            }

    def stop(self, timeout_s: float = 8.0) -> list[tuple[float, float, str]]:
        """End the stream (EOF), wait briefly for the final captions, and return every
        settled caption (recording time) for the draft transcript."""
        try:
            self._queue.put(None, timeout=1.0)
        except queue.Full:
            self.failed = True
            try:
                self._proc.stdin.close()  # type: ignore[union-attr]
            except Exception:
                pass
        deadline = time.monotonic() + timeout_s
        self._reader.join(timeout=max(0.1, deadline - time.monotonic()))
        if self._proc.poll() is None:
            self._proc.kill()
        try:
            self._proc.wait(timeout=2)
        except Exception:
            pass
        for pipe in (self._proc.stdout, self._proc.stderr):
            try:
                if pipe is not None:
                    pipe.close()
            except Exception:
                pass
        with self._lock:
            return list(self._all_settled)
