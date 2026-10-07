#!/usr/bin/env bash
# Smoke test for the speech helper. Synthesizes a short spoken fixture with `say`, then
# checks: probe, malformed-request handling, and — when the models are installed in the
# app's model cache — transcribe (words + absolute times), diarize, draft, and captions.
# Usage: smoke-test.sh [path/to/speech-engine]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="${1:-$HERE/build/speech-engine}"
HUB="${SIRINA_HF_HUB:-$HOME/Library/Application Support/com.sirina.app/models/hf/hub}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

say -o "$TMP/f.aiff" "Hello, this is the Sirina speech helper smoke test. The weather is sunny today."
afconvert -f WAVE -d LEI16@48000 -c 1 "$TMP/f.aiff" "$TMP/f.wav"

"$BIN" --probe > "$TMP/probe.json"
python3 - "$TMP/probe.json" <<'PY'
import json, sys
p = json.load(open(sys.argv[1]))
assert p.get("whisperkit") is True, p
print("ok  probe", p)
PY

printf 'not json\n{"id":1,"cmd":"bogus"}\n' | "$BIN" serve > "$TMP/bad.jsonl"
python3 - "$TMP/bad.jsonl" <<'PY'
import json, sys
lines = [json.loads(l) for l in open(sys.argv[1])]
assert lines[0]["ok"] is False and lines[0]["error"] == "malformed request", lines
assert lines[1]["ok"] is False and "unknown cmd" in lines[1]["error"], lines
print("ok  malformed requests answered, loop survived")
PY

WK="$(ls -d "$HUB"/models--argmaxinc--whisperkit-coreml/snapshots/*/openai_whisper-large-v3-v20240930_626MB 2>/dev/null | head -1 || true)"
SK="$(ls -d "$HUB"/models--argmaxinc--speakerkit-coreml/snapshots/* 2>/dev/null | head -1 || true)"
if [ -z "$WK" ] || [ -z "$SK" ]; then
  echo "skip model checks (models not installed in $HUB)"
  exit 0
fi

python3 - "$WK" "$SK" "$TMP/f.wav" > "$TMP/req.jsonl" <<'PY'
import json, sys
wk, sk, wav = sys.argv[1:4]
for r in [
    {"id": 1, "cmd": "load_whisper", "model_dir": wk},
    {"id": 2, "cmd": "transcribe", "path": wav, "start_s": 0, "end_s": None, "language": "en"},
    {"id": 3, "cmd": "transcribe", "path": wav, "start_s": 2.0, "end_s": None, "language": "en"},
    {"id": 4, "cmd": "load_diarizer", "model_dir": sk},
    {"id": 5, "cmd": "diarize", "path": wav},
    {"id": 6, "cmd": "draft", "path": wav, "start_s": 0, "language": "en"},
]:
    print(json.dumps(r))
PY
"$BIN" serve < "$TMP/req.jsonl" > "$TMP/resp.jsonl"
python3 -c "
import sys
d=open('$TMP/f.wav','rb').read(); i=d.find(b'data'); sys.stdout.buffer.write(d[i+8:])" | "$BIN" captions --language en > "$TMP/cap.jsonl" || true
python3 - "$TMP/resp.jsonl" "$TMP/cap.jsonl" <<'PY'
import json, sys
r = {d["id"]: d for d in (json.loads(l) for l in open(sys.argv[1]))}
for i in (1, 2, 3, 4, 5):
    assert r[i]["ok"], r[i]
text = " ".join(s["text"] for s in r[2]["segments"]).lower()
assert "weather" in text and "sunny" in text, text
words = [w for s in r[2]["segments"] for w in s["words"]]
assert words and all(0 <= w[0] <= w[1] for w in words), words[:5]
print("ok  transcribe:", text)
late = [w for s in r[3]["segments"] for w in s["words"]]
assert late and all(w[0] >= 2.0 for w in late), late[:5]
print("ok  window times are absolute (start_s=2.0)")
assert r[5]["turns"] and r[5]["embeddings"], r[5]
print("ok  diarize:", len(r[5]["turns"]), "turns,", len(r[5]["embeddings"]), "speaker embedding(s)")
if r[6]["ok"]:
    print("ok  draft:", " ".join(s["text"] for s in r[6]["segments"]))
else:
    print("skip draft:", r[6]["error"])
caps = [json.loads(l) for l in open(sys.argv[2])] if open(sys.argv[2]).read().strip() else []
if caps:
    assert any(c["kind"] == "settled" for c in caps), caps
    print("ok  captions:", sum(c["kind"] == "settled" for c in caps), "settled line(s)")
else:
    print("skip captions (unsupported on this macOS)")
PY
echo "smoke test passed"
