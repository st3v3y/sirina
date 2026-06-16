## Context

The app runs as two dev servers (FastAPI on :8000, Vite on :5173) plus an Ollama instance. To use it like Jamie, it should be a single macOS app the user double-clicks. Tauri wraps the existing React build and can run the Python backend as a sidecar; its native layer can also tap system audio via ScreenCaptureKit, removing the BlackHole/Multi-Output requirement.

## Goals / Non-Goals

**Goals:**
- A double-click macOS app: Tauri shell + bundled Python backend (sidecar) + the built UI.
- Microphone + Screen Recording permissions, prompted on first run.
- Unsigned/ad-hoc-signed distribution with a documented Gatekeeper bypass.
- Native ScreenCaptureKit system-audio capture that drops the BlackHole prerequisite.
- Keep `./dev.sh` working for development.

**Non-Goals:**
- Notarization / paid Apple Developer signing.
- Windows/Linux packaging (macOS first).
- Bundling Ollama itself — the app still expects a local Ollama (documented).

## Decisions

- **Two-step delivery.** (1) Package the existing backend as-is so the app works with the current device-based capture (BlackHole still optional). (2) Add native ScreenCaptureKit capture to remove the virtual-device requirement. This lets the app ship before the native-capture work lands.
- **Backend as a Tauri sidecar via PyInstaller.** Freeze the FastAPI app + deps (faster-whisper, pyannote optional, sounddevice) into a single binary; declare it as an `externalBin`; Tauri spawns it on launch (bound to `127.0.0.1` on a chosen/free port) and kills it on quit. The frontend points at that port.
  - *Alternative*: rewrite the backend in Rust. Rejected — throws away the working Python stack.
  - *Risk*: PyInstaller + torch/pyannote is large and finicky; mitigated by making diarization optional and accepting a big bundle, or fetching heavy models/wheels at first run.
- **Model + data caches in a user data dir** (e.g. `~/Library/Application Support/<app>`), not inside the bundle; whisper/pyannote/HF caches and the SQLite DB live there.
- **Native capture in the Tauri/Rust layer.** Use a ScreenCaptureKit binding (Rust crate or a small Swift helper) to capture system audio + CoreAudio mic, streaming PCM frames to the backend over a local socket/IPC. The backend gains a capture source that feeds the **same** `Recorder` pipeline as `sounddevice` (same mic/system/mixed files). Selectable as a recording source in the UI.
- **Permissions/entitlements.** Add `NSMicrophoneUsageDescription` and the Screen Recording usage; Tauri config declares them; first use triggers the macOS prompts.
- **Unsigned distribution.** Build `.app`/`.dmg`; ad-hoc codesign (`codesign --force --deep --sign -`) so it launches; document right-click→Open / `xattr -dr com.apple.quarantine`. No notarization.

## Risks / Trade-offs

- [PyInstaller bundle with torch/faster-whisper/pyannote is very large and can break on import] → Start with a minimal bundle (diarization optional), test the frozen binary early, consider first-run model/dependency fetch. This is the main packaging risk.
- [ScreenCaptureKit binding maturity from Rust] → A small Swift sidecar that streams PCM is a fallback if Rust bindings are insufficient.
- [Gatekeeper friction for unsigned apps] → Unavoidable without notarization; documented one-time bypass. Acceptable for personal/internal use.
- [Port conflicts for the sidecar] → Pick a free ephemeral port at launch and pass it to the frontend.

## Migration Plan

Additive and out-of-process: no schema or API changes for step 1 (packaging). Step 2 adds a capture source; the existing device path remains. Dev flow unchanged.

## Open Questions

- Bundle strategy for heavy ML deps: ship everything in the PyInstaller binary vs fetch models/wheels on first run. Lean: ship code, fetch models on first run (already how whisper/pyannote behave).
- Whether to bundle a managed Ollama or require the user's local Ollama. Lean: require local Ollama (documented), revisit later.
- Exact ScreenCaptureKit integration (Rust crate vs Swift helper) — decide when implementing step 2.
