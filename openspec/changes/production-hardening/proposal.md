## Why

Four deferred follow-ups stand between the current build and a polished, private, fully-functional distributable. They're independent but share one theme — making the packaged local-first app behave correctly outside a dev checkout:

- The app is ad-hoc signed, so macOS re-prompts for Screen Recording permission on every launch.
- Speaker diarization is exposed in settings but inert in the packaged app (no runtime), and the torch-based path would add ~0.5 GB if bundled.
- Secrets (HF token, cloud API keys) are stored as plaintext in the DB.
- The `llm_context_tokens` setting doesn't actually apply to local Ollama, which silently truncates to its own default context.
- The packaged backend is PyInstaller **onefile**, re-extracting the whole bundle to a temp dir on every launch (~20–25 s startup).

## What Changes

- **Stable code signing** so OS permission grants (Screen Recording / TCC) persist across launches and rebuilds: the build script selects/encourages a stable signing identity, fails loudly when falling back to ad-hoc, and the flow is documented. (Distributable signing/notarization beyond a self-signed identity is out of scope.)
- **On-demand ONNX diarization**: instead of bundling torch/pyannote (~0.5 GB), run diarization on the already-bundled `onnxruntime` with an ONNX model that is **downloaded on first enable** (a button), cached under the app data dir. Near-zero bundle increase; diarization stays off by default and opt-in. (Replaces the current torch/pyannote diarizer.)
- **OS-keyring secret storage**: route the existing `secret_get`/`secret_set` seam through the `keyring` library (macOS Keychain / Windows Credential Manager / Linux Secret Service), with the DB as a fallback when no OS backend exists. Migrate any existing plaintext secrets out of the DB.
- **Local context window honored**: for local providers (Ollama), send the configured `llm_context_tokens` as the runtime context (`num_ctx`) so larger windows actually take effect instead of being silently truncated.

**Runtime resilience — the shipped app fails gracefully:**
- **Backend-failure surfacing**: today, if the bundled backend fails to start or exits, the app shows "Starting backend…" forever (the Rust connect-loop and the React gate both wait indefinitely). Surface an actionable error with **retry** after a timeout, and detect when the sidecar exits *after* startup.
- **Persistent logs**: write backend logs to a rotating file under the app data dir (never logging secret values), so issues can be diagnosed after the fact.
- **Model-download resilience**: surface a failed/offline first-run transcription-model download (and offer retry) instead of an endless "loading" state with silently failing transcription.
- **Frontend error boundary**: a render error shows a recoverable message, not a white screen.
- **Branded splash screen**: replace the bare spinner with a paper-and-ink startup screen (logo + serif wordmark, themed) that hosts the startup phase and the failure/retry states above.
- **Minor cleanups**: single-instance (a second launch focuses the existing window rather than spawning a second backend); remove the unused `app_password` config (dead code).

**Startup performance:**
- **Faster launch**: switch the backend from PyInstaller **onefile** to **onedir** (no per-launch re-extraction), and defer heavy engine imports out of startup so the app is usable in a few seconds while the transcription model finishes loading in the background.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `desktop-app`: OS permission grants persist across launches via a stable signing identity (no per-launch re-prompt); backend startup/crash failures are surfaced (not an endless splash); a single instance runs at a time; backend logs are persisted to a rotating file; the app starts promptly (no per-launch re-extraction).
- `app-shell`: the UI recovers from render errors (no white screen); the startup/readiness gate shows actionable errors with retry (backend unreachable, transcription model failed/offline) instead of waiting indefinitely.
- `speaker-diarization`: diarization runs in the packaged app via an on-demand ONNX model (downloaded on first enable) on the bundled `onnxruntime` — no torch bundle.
- `app-settings`: secret settings are stored in the OS keyring (DB fallback) rather than as plaintext in the database.
- `llm-provider`: local providers honor a configured context window so the full prompt is processed, not truncated.

## Impact

- **Packaging**: `scripts/build-macos-app.sh` (signing identity handling), `backend/packaging/backend.spec` (onedir + bundle the sidecar's `_internal`), `docs/PACKAGING.md`.
- **Backend**: `app/settings_store.py` (`secret_get`/`secret_set` → keyring + one-time migration) + `keyring` dep; `app/llm/provider.py` (+ `build_llm`) local-provider native context; a new ONNX `app/processing/diarize.py` (replaces torch/pyannote; drops those deps) + an "is the model downloaded / download it" API; defer engine imports in `main.py`/`transcribe/engine.py`.
- **Secrets/data**: existing plaintext secrets migrated out of the `setting` table into the keyring; behavior otherwise unchanged.
- **Runtime resilience**: `frontend/src-tauri/src/lib.rs` (detect sidecar exit, navigate timeout, single-instance plugin), `frontend/src/App.tsx` + a new error boundary, the React backend gate (actionable errors + retry), `backend/app/main.py` (rotating file logging) and `app/api/status.py` (model-load/ready vs failed state); remove `app_password` from `config.py`.
- **Independence**: the areas are decoupled and can be implemented/verified in any order; the ONNX diarizer is the largest piece of new code.
