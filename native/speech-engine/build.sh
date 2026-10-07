#!/usr/bin/env bash
# Build the speech helper (single binary). Requires Xcode/Swift; fetches WhisperKit 1.1.0
# via SwiftPM on the first build. Runs the smoke test when models are available.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/build"
mkdir -p "$OUT"
cd "$HERE"
swift build -c release --arch arm64
cp "$(swift build -c release --arch arm64 --show-bin-path)/speech-engine" "$OUT/speech-engine"
echo "Built $OUT/speech-engine"
"$OUT/speech-engine" --probe
if [ "${SKIP_SMOKE:-0}" != "1" ]; then
  "$HERE/smoke-test.sh" "$OUT/speech-engine" || { echo "smoke test failed"; exit 1; }
fi
