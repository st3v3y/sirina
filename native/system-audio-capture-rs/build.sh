#!/usr/bin/env bash
# Build the system-audio-capture helper for Linux (and run its unit tests).
# Needs Rust and the PulseAudio client headers (Debian/Ubuntu: libpulse-dev).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
cargo test --quiet
cargo build --release
echo "Built $HERE/target/release/system-audio-capture"
echo "Probe:   target/release/system-audio-capture --probe   (exit 0 = available)"
echo "Capture: target/release/system-audio-capture > out.raw  (48kHz mono s16le)"
