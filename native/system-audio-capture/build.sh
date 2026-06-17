#!/usr/bin/env bash
# Build the system-audio-capture sidecar (single binary). Requires Xcode/Swift.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/build"
mkdir -p "$OUT"

swiftc -O \
  -target arm64-apple-macos13.0 \
  -framework ScreenCaptureKit -framework AVFoundation -framework CoreMedia \
  "$HERE/Sources/system-audio-capture/main.swift" \
  -o "$OUT/system-audio-capture"

echo "Built $OUT/system-audio-capture"
echo "Probe:   $OUT/system-audio-capture --probe   (exit 0 = available)"
echo "Capture: $OUT/system-audio-capture > out.raw  (48kHz mono s16le)"
