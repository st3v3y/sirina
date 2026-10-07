#!/usr/bin/env python3
"""Stand-in for `speech-engine captions`: one settled caption per second of 48 kHz s16 audio.
With FAKE_CAPTIONS_CRASH=1 it exits immediately (helper failure)."""
import json
import os
import sys

if os.environ.get("FAKE_CAPTIONS_CRASH") == "1":
    sys.exit(2)
total = 0
second = 0
while True:
    data = sys.stdin.buffer.read(9600)
    if not data:
        break
    total += len(data) // 2
    while total >= (second + 1) * 48000:
        print(json.dumps({"kind": "provisional", "start": second, "end": second + 0.5, "text": "partial"}), flush=True)
        print(json.dumps({"kind": "settled", "start": second, "end": second + 1, "text": f"second {second}"}), flush=True)
        second += 1
