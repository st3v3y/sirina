## 1. Native sidecar (Swift / ScreenCaptureKit)

- [ ] 1.1 Create `native/system-audio-capture/` Swift package: an `SCStream` with `capturesAudio=true`, `excludesCurrentProcessAudio=true`, 48 kHz mono
- [ ] 1.2 Convert each audio `CMSampleBuffer` to interleaved s16le and write raw bytes to stdout; flush per buffer
- [ ] 1.3 Add a `--probe` mode that verifies the binary runs on this macOS and exits 0 (non-zero on unsupported/permission failure); report permission state on stderr
- [ ] 1.4 Add a build script producing a signed-capable standalone binary; document the contract (48 kHz, mono, s16le, little-endian) in a README

## 2. Backend — availability + capture source

- [ ] 2.1 Add `audio/system_capture.py`: locate the sidecar (`SYSTEM_AUDIO_SIDECAR` env, else bundled path), `native_available()` (exists + `--probe` exits 0), and a `spawn()` helper
- [ ] 2.2 Add `_SidecarTrack` in `recording/recorder.py`: spawn the helper, read fixed-size PCM frames from stdout on a thread, write `system.wav` + update the level meter; `stop()` terminates the process and closes the WAV
- [ ] 2.3 Generalize `recorder.start` to take a `system_source` ("native" | "device" | "none"): native → `_SidecarTrack`; device → existing `_Track(system_device)`; none → no system track
- [ ] 2.4 Terminate any sidecar process on stop/shutdown and kill stale instances on startup (no orphans)

## 3. Backend — API

- [ ] 3.1 Add `GET /api/audio/capabilities` → `{ native_system_audio: bool }`
- [ ] 3.2 Extend the start payload with `system_source` (+ keep `system_device`); default: `system_device` present ⇒ "device", else "none" (backwards-compatible)
- [ ] 3.3 Reject `system_source: "native"` when unavailable (400, actionable message); require `system_device` for "device"
- [ ] 3.4 Surface permission/sidecar-start failure as a clear start error (point to Screen Recording settings); never record a silent system track in its place

## 4. Frontend

- [ ] 4.1 `lib/api.ts`: add `getAudioCapabilities()` and `system_source` on the start request
- [ ] 4.2 `Dashboard.tsx` modal: fetch capabilities on open; if native → show only the mic picker + "system audio captured automatically" note and send `system_source: "native"`
- [ ] 4.3 If native unavailable → keep the current mic + system-device dropdowns (BlackHole fallback), send `system_source: "device"`/"none"; preserve localStorage mic pre-fill
- [ ] 4.4 Show the start error (e.g. permission denied) inline in the modal

## 5. Tauri + docs

- [ ] 5.1 Bundle the sidecar binary with the Tauri app and set `SYSTEM_AUDIO_SIDECAR` to its path when launching the backend (coordinate with `tauri-desktop-app`)
- [ ] 5.2 Add the Screen Recording usage/entitlement so the permission prompt appears; document signing/notarization needs
- [ ] 5.3 README: desktop app → native capture (grant Screen Recording); browser mode → BlackHole loopback setup

## 6. Verification

- [ ] 6.1 In the desktop app, a 2-person call records You (mic) + the other participant (native system) as separate tracks; the system track contains the far-end, not the mic
- [ ] 6.2 `GET /api/audio/capabilities` reports `true` in the desktop app and `false` in browser/dev
- [ ] 6.3 Browser/dev with BlackHole selected still works exactly as before (device path unchanged)
- [ ] 6.4 Requesting native when unavailable returns a 400; denying Screen Recording yields a clear error and no silent system track
- [ ] 6.5 No orphaned sidecar process remains after stop or backend shutdown
- [ ] 6.6 Sidecar PCM plays back correctly (right sample rate/endianness) via the audio player; mixed track has both voices, no feedback of our own playback
