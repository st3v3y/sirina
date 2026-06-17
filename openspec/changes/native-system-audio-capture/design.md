## Context

`recording/recorder.py` captures each track with a PortAudio `sd.InputStream` (`_Track`) whose callback writes mono s16le frames to a WAV at `CAPTURE_SR`. PortAudio can only read **input** devices, so capturing the far-end of a call requires a loopback driver (BlackHole) selected as a second "system" input — fragile and a real source of data loss (a user re-recorded their own mic). macOS exposes the system output mix to apps via **ScreenCaptureKit** (macOS 13+, Screen Recording permission) and **Core Audio process taps** (14.4+) — no loopback device needed. The app is moving to a **Tauri desktop** shell, which can bundle a native helper; the plain browser/dev setup cannot, so it must keep the BlackHole path.

## Goals / Non-Goals

**Goals:**
- In the desktop app, capture system audio natively (no BlackHole, mic-only selection).
- Detect availability at runtime and adapt the UI/start flow.
- Keep the existing PortAudio + BlackHole path working unchanged when native isn't available.
- Reuse the existing track/WAV/mixed pipeline — only the system source changes.

**Non-Goals:**
- Cross-platform native capture (Windows/Linux) — macOS only for now; others use the device path.
- Replacing the microphone capture (mic stays PortAudio).
- Live transcription during capture (unchanged — capture still writes to disk only).
- Building the full Tauri shell here (that's `tauri-desktop-app`); this change defines the sidecar contract and backend/UI integration.

## Decisions

### 1. Native capture lives in a Swift sidecar, not Python
ScreenCaptureKit/Core Audio are Objective-C/Swift APIs with no usable Python binding. **Decision:** ship a tiny standalone Swift binary `system-audio-capture` that:
- starts an `SCStream` with `configuration.capturesAudio = true`, `excludesCurrentProcessAudio = true` (no feedback), sample rate 48 kHz, mono;
- converts each audio `CMSampleBuffer` to interleaved **s16le** and writes raw bytes to **stdout**;
- logs/handles permission denial on stderr with a distinct exit code.
Python treats it as a PCM source: spawn it, read fixed-size frames from stdout on a reader thread, and feed the **same WAV-writer path** used by `_Track`. *Alternatives:* PyObjC (heavy, fragile to package), a Core Audio process-tap aggregate device readable by PortAudio (clever but 14.4+ only and still needs native setup) — sidecar is the simplest portable contract.

### 2. Availability detection
`audio/system_capture.py::native_available()` returns true when a sidecar binary is found (env `SYSTEM_AUDIO_SIDECAR`, else a bundled path relative to the app) **and** a quick `--probe` invocation exits 0 (binary runs on this macOS). The Tauri app sets `SYSTEM_AUDIO_SIDECAR` to the bundled binary; in browser/dev it's unset → not available → fallback. `GET /api/audio/capabilities` → `{ native_system_audio: bool }` drives the UI.

### 3. Recorder integration — a second track source
Generalize the system track so its frames can come from either source, sharing the WAV writer + level meter:
- `_Track` keeps the PortAudio path (mic always; system in fallback mode).
- New `_SidecarTrack` spawns the helper and pumps stdout→WAV on a thread; `stop()` terminates the process and closes the WAV.
The recorder picks the system source from the start request: `system_source = "native"` → `_SidecarTrack`; `"device"` → `_Track(system_device)`; `"none"` → no system track. Mic unchanged.

### 4. Start API + selection rules
Start payload: `{ device (mic), system_source: "native"|"device"|"none", system_device? }`.
- If `system_source == "native"` but native isn't available → 400 (or auto-downgrade to `none` with a warning; **decision:** 400 so the UI never silently loses the far-end).
- If `"device"`, require `system_device`.
- Backwards-compatible default: when the field is absent, treat a provided `system_device` as `"device"`, else `"none"`.

### 5. Frontend modal adaptation
On open, fetch `/api/audio/capabilities`:
- **native available** → show only the **microphone** picker + a line "System audio (other participants) is captured automatically"; send `system_source: "native"`.
- **not available** → current mic + **System audio** device dropdown (BlackHole fallback); send `system_source: "device"` (or `none`). localStorage of last mic still applies.

### 6. Permissions & failure
First `SCStream` use triggers the macOS Screen Recording prompt (handled by the desktop app's TCC entitlement). If denied or the sidecar dies at start, the recorder fails the start cleanly with a message pointing to System Settings → Privacy → Screen Recording, and the user can retry or use the device path. The sidecar excludes the app's own process audio to prevent capturing our own playback.

## Risks / Trade-offs

- **Sidecar packaging/signing** — the binary must be signed/notarized with the app and carry the Screen Recording usage; unsigned dev builds may be blocked. → Mitigation: env-var path for dev; document signing in the Tauri change.
- **macOS version variance** — ScreenCaptureKit audio is 13+; APIs shifted across 13→15. → Mitigation: target a known-good API, `--probe` gate, fall back to device path on probe failure.
- **PCM format mismatch** (sample rate/endianness) between sidecar and WAV writer → garbled audio. → Mitigation: fix the contract (48 kHz, mono, s16le, native-endian little) and assert frame sizes; a short self-test in `--probe`.
- **Process lifecycle** — orphaned sidecar if the backend crashes. → Mitigation: track the PID, terminate on stop/shutdown, and on startup kill stale instances.
- **Feedback loop** — capturing our own playback. → Mitigation: `excludesCurrentProcessAudio = true`.

## Migration Plan

1. Add `audio/system_capture.py` (locate/probe sidecar) + `GET /api/audio/capabilities`.
2. Add `_SidecarTrack` and wire `system_source` into `recorder.start` and the start API (backwards-compatible default).
3. Frontend: capabilities fetch + modal adaptation.
4. Add the Swift sidecar source + a build step; wire `SYSTEM_AUDIO_SIDECAR` in the Tauri bundle (coordinated with `tauri-desktop-app`).
5. Docs. Rollback: without the sidecar/env, `native_available()` is false and everything behaves exactly as today (BlackHole path).

## Open Questions

- Capture the **mic** natively too (single permission, unified clock) or keep PortAudio for mic? Start with PortAudio mic + native system; revisit if clock drift between mic and system matters for mixing.
- On `system_source: native` failure, hard-fail vs. auto-fallback to device — chosen hard-fail (400) to avoid silently losing the far-end; revisit if users prefer auto-fallback.
- Core Audio process tap (14.4+) as an alternative/again-native mic+system aggregate — deferred; ScreenCaptureKit covers 13+.
