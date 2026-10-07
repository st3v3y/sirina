#!/usr/bin/env python3
"""Stand-in for `speech-engine serve` in tests: same JSON-lines protocol.

transcribe → one segment spanning the window with two words (absolute times).
crash_once → exits the first time it is asked (state in $FAKE_HELPER_STATE), to test restart.
"""
import json
import os
import sys

state = os.environ.get("FAKE_HELPER_STATE", "")
loaded = set()
for line in sys.stdin:
    req = json.loads(line)
    rid, cmd = req.get("id"), req.get("cmd")
    if cmd == "crash_once" and state and not os.path.exists(state):
        open(state, "w").close()
        sys.exit(1)
    if cmd and cmd.startswith("load_"):
        loaded.add(cmd)
        resp = {}
    elif cmd == "transcribe":
        if "load_whisper" not in loaded:
            print(json.dumps({"id": rid, "ok": False, "error": "whisper model not loaded"}), flush=True)
            continue
        s, e = req["start_s"], req.get("end_s") or req["start_s"] + 10
        resp = {"segments": [{"start": s + 1, "end": e - 1, "text": "hello world",
                              "words": [[s + 1, s + 2, "hello"], [s + 2, e - 1, "world"]]}],
                "language": req.get("language") or "en"}
    elif cmd == "crash_once":
        resp = {"survived": True}
    else:
        print(json.dumps({"id": rid, "ok": False, "error": f"unknown cmd {cmd}"}), flush=True)
        continue
    print(json.dumps({"id": rid, "ok": True, **resp}), flush=True)
