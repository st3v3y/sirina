## Context

Four follow-ups deferred from earlier changes, all about the app behaving correctly outside a dev checkout. Current state:
- `scripts/build-macos-app.sh` signs with `CODESIGN_IDENTITY` or ad-hoc (`-`); ad-hoc means macOS TCC re-prompts for Screen Recording every launch.
- `app/processing/diarize.py` lazy-imports pyannote.audio; `backend/packaging/backend.spec` bundles only `frontend_dist` + collected packages, so pyannote/torch aren't in the packaged app.
- `app/settings_store.py` has a `secret_get`/`secret_set` seam that is DB-backed (plaintext in the `setting` table).
- The LLM seam is OpenAI-compatible (`/v1/chat/completions`); the `llm_context_tokens` setting sizes the cross-chat budget but isn't sent to Ollama, which truncates to its own default `num_ctx`.

## Goals / Non-Goals

**Goals:** persistent OS permissions via stable signing; diarization that actually runs in the packaged app; secrets in the OS keyring (DB fallback); the local context-window setting honored by Ollama.

**Non-Goals:** Apple Developer ID signing / notarization / Gatekeeper distribution (self-signed identity only); Windows/Linux packaging work beyond what keyring brings; new diarization features; RAG/retrieval for chat; auto-detecting a model's max context (see prior decision — model-max ≠ runtime context).

## Decisions

### 1. Stable code signing
The build script resolves a signing identity in order: explicit `CODESIGN_IDENTITY` → a single local **"Code Signing"** self-signed identity if exactly one is found (`security find-identity -p codesigning`) → ad-hoc `-`. When it lands on ad-hoc, it prints a clear warning that OS permissions will re-prompt and points at the cert-creation steps. `docs/PACKAGING.md` documents creating a self-signed "Code Signing" cert in Keychain Access. The capture sidecar keeps being signed with the app's bundle identifier (so TCC treats it as the same client). *Out of scope:* anything requiring an Apple Developer account.

### 2. On-demand ONNX diarization (no torch bundle)
Measured: bundling torch/pyannote would add ~0.5 GB (torch is ~430 MB on macOS arm64). Instead, **reuse the already-bundled `onnxruntime` (68 MB)** and run an ONNX diarizer, with the model **downloaded on demand**:
- Replace the torch/pyannote `Diarizer` (`app/processing/diarize.py`) with an ONNX implementation (candidate: `sherpa-onnx` segmentation+embedding, or pyannote exported to ONNX). Drop the `pyannote.audio`/`torch`/`torchaudio` deps.
- The ONNX model is **not** bundled. A small API reports whether it's present and downloads it on request; the Settings "Enable diarization" flow has an **Install / Download** step that fetches it once into the data dir (`HF_HOME`), after which it can be enabled. Off by default.
- `backend.spec` then needs no torch hooks; only onnxruntime (already present) ships.
*Trade-off:* a new diarizer implementation (real work) in exchange for ~zero bundle growth and a pay-only-if-you-want-it model. The `diarization_model` setting's options change to the ONNX model id(s).
*Alternative considered:* bundle torch (~+0.5 GB, reuse the existing pyannote path) — rejected for the size, per the user's preference to download diarization on demand.

### 3. Secrets in the OS keyring
Add the `keyring` dependency and reimplement the existing seam:
- `secret_set(key, value)` → `keyring.set_password(SERVICE, key, value)` where `SERVICE` is the app bundle id; on `keyring` failure/unavailability, fall back to the DB `setting` row (today's behavior). Also keep the in-memory `settings` attr in sync.
- `secret_get(key)` → effective value (keyring → DB fallback → `.env`/default), used only for truthiness in the API.
- **Startup migration** (`load_overrides` or a dedicated step): for each registry secret field, if a plaintext value exists in the `setting` table and a keyring backend is available, move it into the keyring and delete the DB row.
Call sites (the `app-settings` `apply()` path, `GET /api/settings` masking) are unchanged — that's the point of the seam. *Risk:* on macOS, Keychain access is tied to the app's signature; pairs naturally with decision 1. Headless/Linux without a Secret Service backend → DB fallback (logged).

### 4. Local providers honor the context window
Give `OpenAICompatProvider` an optional native-Ollama path. `build_llm()` sets `ollama_native=True` when the provider preset is `ollama`. When set, `generate()` posts to `{root}/api/chat` (root = base_url without `/v1`) with `{model, messages, stream:false, options:{num_ctx: settings.llm_context_tokens}}` and reads `message.content`; otherwise it uses the OpenAI `/v1/chat/completions` path unchanged. `ping`/`list_models` stay on the existing endpoints. Cloud and LM Studio are untouched (LM Studio honors the loaded model's context; no portable num_ctx knob). *Alternative considered:* passing `num_ctx` through `/v1` — rejected, Ollama ignores it there.

### 5. Runtime resilience
- **Backend-failure surfacing.** In `lib.rs`, the connect-loop gets a max-wait; on timeout (or on a `CommandEvent::Terminated` from the sidecar) the app surfaces an actionable error instead of looping forever, and offers retry (re-spawn). Replace the `.expect()` on spawn with a graceful error path. The React `BackendGate` similarly caps its `/api/status` polling and renders a "couldn't reach the backend" view with retry, distinguishing "still starting / first-run download" (keep waiting, with the existing hint) from "gave up" (error). Use a generous threshold so a slow first-run model download isn't misreported as failure.
- **Persistent logs.** Add a `RotatingFileHandler` writing to `data_dir/logs/sirina.log` alongside the existing stdout handler (`main.py`). Secrets already aren't logged; keep it that way (the secret seam never logs values).
- **Model readiness.** `/api/status` reports the transcription model as `loading | ready | failed` (today it's only loaded-or-not). The background `whisper.load()` records a failure instead of leaving `whisper_loaded=false` forever; the sidebar/status surfaces `failed` with a retry (re-trigger load) so an offline first-run download is visible rather than a silent perpetual "loading".
- **Frontend error boundary.** A React error boundary wraps the routed content (inside the shell) and renders a recoverable message + reload on a render throw.
- **Branded splash.** The `BackendGate` loading view becomes a paper-and-ink splash: the `sirina-mark.svg` logo + serif "Sirina" wordmark on a themed background, a refined (vermilion) loading indicator, and the phase text. It's one component that also renders the "still downloading / unreachable / model failed" + retry states from above. It needs no backend (just the bundled logo + fonts), so it renders correctly in both the pre-navigation `tauri://` phase and the post-navigation `http://` phase. Respect `prefers-reduced-motion`.
- **Single instance + cleanup.** Add `tauri-plugin-single-instance` so a second launch focuses the existing window (no second sidecar/port). Remove the unused `app_password` field from `config.py` (dead code — never read; the local API is already loopback-only on an ephemeral port).

### 6. Startup performance
The packaged backend is PyInstaller **onefile**, which re-extracts the whole bundle (mlx, ctranslate2, onnxruntime, frozen Python — hundreds of MB) to a temp dir on every launch (~20–25 s observed in the logs as a fresh `/T/_MEIxxxx` each run).
- **Switch to `onedir`** in `backend.spec` (`EXE(exclude_binaries=True)` + `COLLECT(...)`): the libs live in a folder and aren't re-extracted each launch. *Caveat:* the Tauri sidecar mechanism expects a single executable, so the onedir `_internal` folder must be bundled alongside the sidecar binary (adjust `backend.spec`, the copy step in `build-macos-app.sh`, and the Tauri resource bundling) — this is the fiddly part.
- **Defer heavy imports**: `select_engine()` runs in lifespan and pulls in mlx/faster-whisper before `/api/status` answers. Defer engine construction/imports so the backend reports ready quickly and the model loads in the background (the sidebar already shows `whisper_state`), shortening the splash regardless of onefile/onedir.

## Risks / Trade-offs

- **New ONNX diarizer accuracy/parity** → a different model than pyannote; quality may differ, and it's net-new code. → Mitigation: keep it opt-in/off by default; validate on a known multi-speaker recording; the baseline two-track split still works without diarization.
- **onedir + Tauri sidecar packaging** → the sidecar's `_internal` folder must travel with the binary or the packaged backend won't start. → Mitigation: verify with a real `./scripts/build-macos-app.sh` run before relying on it; the onefile fallback remains if onedir proves too fiddly.
- **Keyring availability/prompts** → first keyring access on macOS can prompt; unsigned/ad-hoc apps get a fresh keychain identity. → Mitigation: stable signing (decision 1); DB fallback when no backend; never block startup on keyring errors.
- **Native-Ollama path divergence** → a second request shape to maintain. → Mitigation: keep it minimal (only `generate`, only when `ollama_native`); the OpenAI path stays the default for everything else.
- **Signing is partly a user action** (creating the cert) → can't be fully automated. → Mitigation: detect + document; the script still works ad-hoc with a clear warning.
- **False-positive backend failure** (a slow first-run model download mistaken for a crash) → Mitigation: only the *backend process* exit / unreachability triggers the error; model download is a separate `loading→ready|failed` signal with a generous threshold and a "still downloading" hint.
- **Single-instance plugin behavior** varies by platform → Mitigation: target macOS (the current build); focus-existing on second launch; verify it doesn't interfere with the dev (`./dev.sh`) flow, which doesn't use the Tauri shell.

## Migration Plan

1. Signing + docs (no runtime change; affects packaged builds).
2. Keyring seam + startup migration (idempotent; DB fallback preserves current behavior).
3. Local-Ollama `num_ctx` path (additive; cloud unchanged).
4. Bundle pyannote/torch (heaviest; verify a packaged diarized recording).
Rollback per area: revert the relevant commit. Keyring migration is one-way per secret but the value is preserved (just relocated); a manual re-entry always works.

## Open Questions

- Bundle `torch` CPU-only to cap size, or include MPS? (Lean: whatever the existing pyannote MPS path needs on Apple Silicon; revisit size after a first build.)
- Keyring `SERVICE`/account scheme — bundle id + setting key (chosen) vs a single composite blob. (Lean: per-key, simplest.)
- Should the native-Ollama path also back `ask`/`summarize`/`cross_ask` (it does, via `generate`) or only cross-chat? (It backs all `generate` calls — consistent and desirable.)
