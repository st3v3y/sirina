## 1. Stable code signing

- [x] 1.1 In `scripts/build-macos-app.sh`, resolve the signing identity in order: `CODESIGN_IDENTITY` → a single local "Code Signing" self-signed identity (`security find-identity -p codesigning`) → ad-hoc `-`
- [x] 1.2 When falling back to ad-hoc, print a clear warning that OS permissions (Screen Recording) will re-prompt, and point at the cert-creation steps
- [x] 1.3 Document creating a self-signed "Code Signing" certificate (Keychain Access) and the `CODESIGN_IDENTITY` flow in `docs/PACKAGING.md`
- [ ] 1.4 Verify: build with a stable identity, grant Screen Recording, relaunch → no re-prompt

## 2. OS-keyring secret storage

- [x] 2.1 Add the `keyring` dependency to `backend/pyproject.toml`
- [x] 2.2 Reimplement `secret_set` to write to the OS keyring (service = bundle id, account = setting key), falling back to the DB `setting` row when no keyring backend is available; keep the `settings` attr in sync
- [x] 2.3 Reimplement `secret_get` to read the effective value (keyring → DB fallback → `.env`/default); API masking/`is_set` unchanged
- [x] 2.4 Add an idempotent startup migration: when a keyring is available, move any plaintext secret from the `setting` table into the keyring and delete the DB row
- [x] 2.5 Verify: save the HF token → stored in the keyring, not plaintext in the DB; reading still works; no-keyring environment falls back to the DB

## 3. Local context window honored (Ollama)

- [x] 3.1 Add an optional native-Ollama path to `OpenAICompatProvider` (`ollama_native` flag); `build_llm()` sets it when the provider preset is `ollama`
- [x] 3.2 When native, `generate()` POSTs `{root}/api/chat` with `options.num_ctx = settings.llm_context_tokens` and reads `message.content`; otherwise use the existing `/v1/chat/completions` path unchanged
- [x] 3.3 Leave cloud + LM Studio on the OpenAI-compatible path (no local-only params sent); `ping`/`list_models` unchanged
- [ ] 3.4 Verify: with Ollama, a transcript larger than the default context is fully considered when `llm_context_tokens` is raised (no mid-prompt truncation)

## 4. Bundle the diarization runtime

- [ ] 4.1 Bundle `pyannote.audio` + `torch`/`torchaudio` in `backend/packaging/backend.spec` via `collect_all(...)` (datas/binaries/hiddenimports), adding hooks as the build surfaces missing modules
- [ ] 4.2 Ensure weights download once on first enable and cache under the app data dir (`HF_HOME`); diarization stays gated by the HF token and off by default
- [ ] 4.3 Confirm the bundled torch uses CPU/MPS consistent with the existing pyannote path
- [ ] 4.4 Verify: in the packaged app, enable diarization with a valid token and process a recording → speakers are separated; weights are reused on the next run

## 5. Runtime resilience + cleanups

- [ ] 5.1 In `lib.rs`, replace the spawn `.expect()` and the unbounded connect-loop with a bounded wait; on timeout or sidecar exit (`CommandEvent::Terminated`), surface an error to the webview and offer retry (re-spawn)
- [x] 5.2 In the React `BackendGate`, cap `/api/status` polling and render an actionable "backend unreachable" view with retry, while still tolerating a slow first-run model download
- [x] 5.3 Report the transcription model state in `/api/status` as loading | ready | failed; record `whisper.load()` failures instead of an indefinite "loading"; surface `failed` + retry in the sidebar/status
- [x] 5.4 Add a rotating file log handler (`data_dir/logs/sirina.log`) alongside stdout in `main.py`; confirm no secrets are written
- [x] 5.5 Add a React error boundary around the routed content; show a recoverable message + reload on a render throw
- [ ] 5.6 Add `tauri-plugin-single-instance` (focus the existing window on a second launch); remove the unused `app_password` from `config.py`
- [x] 5.7 Upgrade the startup splash (the `BackendGate` view): branded paper-and-ink screen (logo + serif wordmark, themed, vermilion loading indicator) showing the phase, and hosting the unreachable / model-failure + retry states; respect `prefers-reduced-motion`; works in both the tauri:// and http:// phases

## 6. Verification

- [ ] 6.1 OS permission grant persists across launches/rebuilds with a stable identity; ad-hoc build prints the warning
- [ ] 6.2 Secrets live in the OS keyring (DB fallback when unavailable); existing plaintext secret is migrated and removed from the DB
- [ ] 6.3 Local Ollama honors the configured context window; cloud requests stay OpenAI-compatible (no `num_ctx`)
- [ ] 6.4 Packaged app runs diarization end-to-end; default (diarization off) path and bundle still launch cleanly
- [ ] 6.5 Backend failure (killed sidecar / forced startup error) shows an actionable error + retry, not an endless splash; a second launch focuses the existing window
- [ ] 6.6 Offline first run surfaces a model-unavailable error with retry (not a perpetual "loading"); a forced render error shows the error boundary, not a blank screen
- [ ] 6.7 Startup splash is branded/themed (logo + wordmark), shows the phase, and renders correctly in light and dark
- [ ] 6.8 A rotating log file is written under the data dir with no secrets
- [ ] 6.9 `npm run build` and a full `./scripts/build-macos-app.sh` succeed
