## Why

Capturing the far-end of a call (everyone else) currently requires the user to install BlackHole and select it as a second "system audio" device — fragile and easy to misconfigure (a real user just re-recorded their own mic and lost the other speaker entirely). Apps like Jamie avoid this: macOS lets an app tap the **system audio output** natively via ScreenCaptureKit (Screen Recording permission), so only the microphone needs selecting and the other participants are always captured. We want that experience in the Tauri desktop app, while keeping the BlackHole device-loopback path working when running in a plain browser (where native capture isn't available).

## What Changes

- **Native system-audio capture (desktop app)**: A bundled macOS helper ("sidecar") captures the system output mix via ScreenCaptureKit and streams PCM to the backend as the `system` track — no virtual device, no second device pick. The app's own audio is excluded to avoid feedback.
- **Capability detection**: The backend reports whether native system-audio capture is available (sidecar present + runnable). The frontend adapts.
- **BlackHole fallback (browser / no sidecar)**: When native capture isn't available, the existing PortAudio "system audio" input-device path remains, with BlackHole as the documented loopback. Behavior unchanged in that mode.
- **Simplified start flow when native is available**: The device modal only asks for the **microphone**; system audio is captured automatically. When native is unavailable it still offers the system-audio device dropdown.
- **Permissions handling**: First native capture triggers the macOS Screen Recording permission prompt; if denied or capture fails, the system surfaces a clear error and can fall back to the device path.

## Capabilities

### New Capabilities

- `native-system-audio-capture`: Capture the macOS system output mix natively (no loopback device) in the desktop app, detect availability, and select native vs. device-loopback as the system-audio source.

### Modified Capabilities

- `audio-recording`: The `system` track MAY be sourced from native capture (when available) or from a selected loopback input device (fallback); the captured tracks and files are otherwise unchanged.
- `device-selection-modal`: When native system-audio capture is available, the start modal hides the system-audio device picker and only asks for the microphone.

## Impact

- **New native component**: a small Swift binary (`system-audio-capture`) using ScreenCaptureKit (`SCStream`, `capturesAudio`, `excludesCurrentProcessAudio`) that emits raw PCM (48 kHz, s16le) on stdout. Built and bundled by the Tauri app as a sidecar; absent in the pure-web/dev setup. Requires macOS 13+ and Screen Recording permission.
- **Backend**:
  - `recording/recorder.py`: add a sidecar-fed system track (spawn the helper, read PCM from its stdout on a thread, write `system.wav`) alongside the existing PortAudio `_Track`; select the source per request/availability.
  - New `audio/system_capture.py`: locate the sidecar (env `SYSTEM_AUDIO_SIDECAR` or bundled path), probe runnability, expose `native_available()`.
  - `api/audio.py` (or status): `GET /api/audio/capabilities` → `{ native_system_audio: bool }`.
  - `api/recordings.py`: start payload gains a system-source selector (`system_source: "native" | "device" | "none"`, with `system_device` for the device case); validate against availability.
- **Frontend**:
  - `lib/api.ts`: `getAudioCapabilities()`; extend the start request with `system_source`.
  - `Dashboard.tsx` modal: if `native_system_audio`, show only the mic picker + a "System audio captured automatically" note; else keep the current mic + system-device dropdowns (BlackHole fallback).
- **Tauri**: declare the sidecar binary, pass its path to the backend (env), and ensure the app requests/holds Screen Recording permission. (Builds on the existing `tauri-desktop-app` change.)
- **Docs**: README note — desktop app needs Screen Recording permission; browser mode needs BlackHole.
- **No DB schema change**: still produces `mic`/`system`/`mixed` tracks; only the system source differs.
