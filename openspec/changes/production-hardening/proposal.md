## Why

Four deferred follow-ups stand between the current build and a polished, private, fully-functional distributable. They're independent but share one theme — making the packaged local-first app behave correctly outside a dev checkout:

- The app is ad-hoc signed, so macOS re-prompts for Screen Recording permission on every launch.
- Speaker diarization is exposed in settings but inert in the packaged app (pyannote/torch aren't bundled).
- Secrets (HF token, cloud API keys) are stored as plaintext in the DB.
- The `llm_context_tokens` setting doesn't actually apply to local Ollama, which silently truncates to its own default context.

## What Changes

- **Stable code signing** so OS permission grants (Screen Recording / TCC) persist across launches and rebuilds: the build script selects/encourages a stable signing identity, fails loudly when falling back to ad-hoc, and the flow is documented. (Distributable signing/notarization beyond a self-signed identity is out of scope.)
- **Bundled diarization runtime**: package pyannote.audio + torch so diarization actually runs in the packaged app, with model weights cached under the app data dir on first use. Diarization stays off by default and opt-in. **BREAKING (packaging):** materially larger app bundle.
- **OS-keyring secret storage**: route the existing `secret_get`/`secret_set` seam through the `keyring` library (macOS Keychain / Windows Credential Manager / Linux Secret Service), with the DB as a fallback when no OS backend exists. Migrate any existing plaintext secrets out of the DB.
- **Local context window honored**: for local providers (Ollama), send the configured `llm_context_tokens` as the runtime context (`num_ctx`) so larger windows actually take effect instead of being silently truncated.

**Runtime resilience — the shipped app fails gracefully:**
- **Backend-failure surfacing**: today, if the bundled backend fails to start or exits, the app shows "Starting backend…" forever (the Rust connect-loop and the React gate both wait indefinitely). Surface an actionable error with **retry** after a timeout, and detect when the sidecar exits *after* startup.
- **Persistent logs**: write backend logs to a rotating file under the app data dir (never logging secret values), so issues can be diagnosed after the fact.
- **Model-download resilience**: surface a failed/offline first-run transcription-model download (and offer retry) instead of an endless "loading" state with silently failing transcription.
- **Frontend error boundary**: a render error shows a recoverable message, not a white screen.
- **Branded splash screen**: replace the bare spinner with a paper-and-ink startup screen (logo + serif wordmark, themed) that hosts the startup phase and the failure/retry states above.
- **Minor cleanups**: single-instance (a second launch focuses the existing window rather than spawning a second backend); remove the unused `app_password` config (dead code).

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `desktop-app`: OS permission grants persist across launches via a stable signing identity (no per-launch re-prompt); backend startup/crash failures are surfaced (not an endless splash); a single instance runs at a time; backend logs are persisted to a rotating file.
- `app-shell`: the UI recovers from render errors (no white screen); the startup/readiness gate shows actionable errors with retry (backend unreachable, transcription model failed/offline) instead of waiting indefinitely.
- `speaker-diarization`: diarization runs in the packaged app (bundled runtime + cached weights), not only in a dev checkout.
- `app-settings`: secret settings are stored in the OS keyring (DB fallback) rather than as plaintext in the database.
- `llm-provider`: local providers honor a configured context window so the full prompt is processed, not truncated.

## Impact

- **Packaging**: `scripts/build-macos-app.sh` (signing identity handling), `backend/packaging/backend.spec` (bundle pyannote/torch), `docs/PACKAGING.md`. Larger bundle + longer build.
- **Backend**: `app/settings_store.py` (`secret_get`/`secret_set` → keyring + one-time migration), a new `keyring` dependency; `app/llm/provider.py` (+ `build_llm`) for a local-provider native context path; `app/processing/diarize.py` only if bundling needs load tweaks.
- **Secrets/data**: existing plaintext secrets migrated out of the `setting` table into the keyring; behavior otherwise unchanged.
- **Runtime resilience**: `frontend/src-tauri/src/lib.rs` (detect sidecar exit, navigate timeout, single-instance plugin), `frontend/src/App.tsx` + a new error boundary, the React backend gate (actionable errors + retry), `backend/app/main.py` (rotating file logging) and `app/api/status.py` (model-load/ready vs failed state); remove `app_password` from `config.py`.
- **Independence**: the areas are decoupled and can be implemented/verified in any order; only the diarization bundling is heavy.
