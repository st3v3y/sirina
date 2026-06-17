## Why

The end goal is a real macOS app the user can launch like Jamie — not two dev servers. Tauri wraps the existing React UI and runs the Python backend as a sidecar, giving a double-click app with first-run Microphone/Screen-Recording permissions. See [docs/V2-LOCAL-REDESIGN.md §5, §13](../../../docs/V2-LOCAL-REDESIGN.md).

> **Scope note (split):** native ScreenCaptureKit system-audio capture is owned by the separate **`native-system-audio-capture`** change. This change is the **shell + Python sidecar + packaging** only. The desktop app declares the Screen Recording permission so the native capture can use it once that change lands, but the capture implementation lives there.

## What Changes

- Wrap the frontend in a **Tauri app** that spawns the Python backend as a **sidecar** (PyInstaller binary) and talks to it on localhost.
- Declare **Microphone** and **Screen Recording** permissions; prompt on first run.
- Ship as an **unsigned macOS app** (no Apple Developer subscription): ad-hoc codesign locally so it launches; document the one-time Gatekeeper bypass (right-click → Open / clear quarantine).
- Point the SQLite DB and whisper/pyannote/HF model caches at a **user data dir** so the packaged app reads/writes outside the bundle.
- Keep the `./dev.sh` two-server flow for development; Tauri is the distribution wrapper.

## Capabilities

### New Capabilities
- `desktop-app`: Tauri packaging of the UI + Python sidecar, permissions, and unsigned macOS distribution.

> Native system-audio capture (`native-audio-capture` / `native-system-audio-capture`) and the `audio-recording` modification are handled by the **`native-system-audio-capture`** change, not here.

## Impact

- **New**: Tauri project (Rust shell), PyInstaller packaging of the backend, app entitlements/usage descriptions, build scripts for `.app`/`.dmg`.
- **Backend**: bind to `127.0.0.1` on a chosen port; locate the DB + model/HF caches in a user data dir (`APP_DATA_DIR`), defaulting to the current `./data` in dev.
- **Distribution**: ad-hoc signing + documented quarantine bypass; first-run permission prompts.
- **Depends on**: a stable core (`record-to-file` + `offline-transcription`, both shipped). The Screen Recording permission declared here is consumed by the `native-system-audio-capture` change.
