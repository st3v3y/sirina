## Why

Sirina only ships for macOS on Apple Silicon. The Tauri shell, the FastAPI backend, the microphone path (PortAudio via `sounddevice`) and faster-whisper already run anywhere. What keeps Windows and Linux users out is the system-audio helper (ScreenCaptureKit), a few macOS command-line tools (`pkill`, `afconvert`, `pmset`) and a build that only produces a macOS `.app`. Recording a call (mic plus the far end) is the core of the product, so it is the first thing to bring to Windows and Linux. Fast transcription and live captions follow in `parakeet-engine-captions`.

## What Changes

- **New native system-audio helper for Windows and Linux**: one small Rust binary.
  - It keeps the existing helper contract: `--probe` with exit codes 0/2/3/4, then 48 kHz mono s16le PCM on stdout until it is terminated. `_SidecarTrack` and the restart and watchdog logic therefore work unchanged.
  - Windows: WASAPI process loopback that excludes Sirina's own process tree. If that is not available, it falls back to plain endpoint loopback.
  - Linux: the PulseAudio API (also served by PipeWire) records the default sink's monitor.
- **Platform-neutral backend utilities**:
  - Orphaned capture helpers are cleaned up without `pkill`.
  - Idle sleep is blocked on Windows (`SetThreadExecutionState`) and Linux (a logind inhibitor through `systemd-inhibit`).
  - The power state (AC or battery) is read through `psutil`.
  - AAC compression and decompression use PyAV instead of `afconvert`, on every platform including macOS. That keeps one code path and lets `.m4a` recordings be re-processed anywhere.
- **Platform-aware capabilities and copy**: `/api/audio/capabilities` and the helper status report which features exist on this platform, each with a reason when one doesn't. UI text that says "this Mac" or "managed by macOS" becomes platform-neutral, or is chosen per platform.
- **Desktop packaging for Windows and Linux**:
  - Tauri bundles an NSIS installer for Windows, and an AppImage plus a `.deb` for Linux.
  - Each OS bundles its own helper names (`.exe` on Windows), and the shell resolves them per platform.
  - The PyInstaller spec no longer hard-codes `arm64`.
- **CI builds**: a GitHub Actions matrix (macOS arm64, Windows x64, Linux x64) builds the frontend, the backend, the native helpers and the Tauri bundle. It also runs the backend tests on every OS and uploads the bundles as artifacts. CI does not sign or release anything.
- **Docs**: the README, `CONTRIBUTING.md` and `docs/PACKAGING.md` cover Windows and Linux: install, the SmartScreen and AppImage notes, how system audio works there, and the known limits.

## Capabilities

### New Capabilities
- `platform-support`:
  - which platforms are supported and what each feature does on each one
  - how unavailable features are reported, with a reason
  - platform-neutral sleep prevention, compression and helper cleanup
  - CI builds for every platform

### Modified Capabilities
- `native-system-audio-capture`:
  - Native capture covers Windows (WASAPI loopback) and Linux (PulseAudio/PipeWire monitor) as well as macOS.
  - The rule to exclude Sirina's own audio becomes "where the platform allows it", and the exception is reported.
  - The permission-failure rule is generalized to any helper start failure.
- `desktop-app`:
  - The single launchable app covers macOS, Windows and Linux.
  - Unsigned-distribution steps cover Windows SmartScreen and Linux AppImage.
  - Permission prompts stay macOS-specific.

## Impact

- **New code**:
  - `native/system-audio-capture-rs/`: a Rust crate with `wasapi` (Windows) and `libpulse-simple-binding` (Linux) dependencies.
  - `.github/workflows/build.yml`.
- **Backend**:
  - `audio/system_capture.py`: helper cleanup and the binary name.
  - `audio/power.py`: Windows and Linux sleep blockers, and the power state through `psutil`.
  - `processing/compress.py`: PyAV encode and decode.
  - `api/audio.py`: capability reasons.
  - `main.py`: startup cleanup.
  - `packaging/backend.spec`: target architecture.
  - `speech_models.py`: hide the macOS-only models on other platforms.
  - New direct dependencies `psutil` and `av` (PyAV is already bundled as a faster-whisper dependency).
  - Two tests that fake helpers with `#!/bin/sh` scripts become portable.
- **Shell**:
  - `frontend/src-tauri/src/lib.rs`: resolve resources per platform, add `.exe` on Windows, skip `speech-engine` where it doesn't exist.
  - `tauri.conf.json`: bundle targets, icons (`.ico`, `.png`), resources per platform through `tauri.windows.conf.json` and `tauri.linux.conf.json`.
  - `capabilities/default.json`: remove the stale shell-sidecar allow-list entry.
- **Frontend**: copy in `Shell.tsx`, `SpeechModels.tsx`, `RecordingDetail.tsx` and `Settings.tsx`, plus the type of `helper.macos` in `api.ts`.
- **Scripts**: `scripts/build-windows.ps1` and `scripts/build-linux.sh`, next to the existing `build-macos-app.sh`.
- **Out of scope**:
  - fast transcription, live captions and live transcription on Windows and Linux (`parakeet-engine-captions`)
  - speaker splitting on Windows and Linux. A later change with sherpa-onnx; until then the existing mic/system split applies.
  - code signing for Windows and Linux
  - ARM builds for Windows and Linux
- **Depends on**: none. It can be implemented in parallel with `parakeet-engine-captions`. It touches requirements that `harden-system-audio-capture` also adds (sleep prevention, helper restart). This change only adds platform coverage on top of them.
