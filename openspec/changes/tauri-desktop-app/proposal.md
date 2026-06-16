## Why

The end goal is a real macOS app the user can launch like Jamie — not two dev servers. Tauri wraps the existing React UI and runs the Python backend as a sidecar, and (critically) its native layer can capture system audio via ScreenCaptureKit, removing the BlackHole/Multi-Output setup entirely. See [docs/V2-LOCAL-REDESIGN.md §5, §13](../../../docs/V2-LOCAL-REDESIGN.md).

## What Changes

- Wrap the frontend in a **Tauri app** that spawns the Python backend as a **sidecar** (PyInstaller binary) and talks to it on localhost.
- Declare **Microphone** and **Screen Recording** permissions; prompt on first run.
- Ship as an **unsigned macOS app** (no Apple Developer subscription): ad-hoc codesign locally so it launches; document the one-time Gatekeeper bypass (right-click → Open / clear quarantine).
- Add **native system-audio capture via ScreenCaptureKit** (Rust/Swift in the Tauri layer) streaming PCM to the backend, so recording works against any output device with **no BlackHole**.
- Keep the `./dev.sh` two-server flow for development; Tauri is the distribution wrapper.

## Capabilities

### New Capabilities
- `desktop-app`: Tauri packaging of the UI + Python sidecar, permissions, and unsigned macOS distribution.
- `native-audio-capture`: ScreenCaptureKit-based system-audio capture (+ CoreAudio mic) replacing the virtual-device requirement.

### Modified Capabilities
- `audio-recording`: system audio may be sourced from native capture instead of a virtual audio device, removing the BlackHole/Multi-Output prerequisite.

## Impact

- **New**: Tauri project (Rust shell), PyInstaller packaging of the backend, app entitlements/usage descriptions, build scripts for `.app`/`.dmg`.
- **Backend**: accept audio frames from the native capture channel as an alternative to `sounddevice`; bind to `127.0.0.1` with a chosen port; bundle/locate model caches in a user data dir.
- **Distribution**: ad-hoc signing + documented quarantine bypass; first-run permission prompts.
- **Depends on**: a stable core (at minimum `record-to-file` + `offline-transcription`). Two-step: (1) package the Python sidecar as-is; (2) add native ScreenCaptureKit capture.
