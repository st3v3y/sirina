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

## 4. On-demand ONNX diarization

- [ ] 4.1 Replace the torch/pyannote `Diarizer` (`app/processing/diarize.py`) with an ONNX implementation on the bundled `onnxruntime` (candidate: sherpa-onnx segmentation+embedding, or pyannote-onnx); keep the existing diarize/turns interface so `job.py` is unchanged
- [ ] 4.2 Drop the `pyannote.audio` / `torch` / `torchaudio` dependencies; update the `diarization_model` setting's options to the ONNX model id(s)
- [ ] 4.3 Add a model-presence + download API (e.g. `GET/POST /api/diarization/model`): the model downloads on demand into the data dir (`HF_HOME`) and is reused; diarization stays off by default and can only be enabled once the model is present
- [ ] 4.4 Settings UI: an "Install / Download" step for diarization (download progress/result), then allow enabling
- [ ] 4.5 Verify: fresh app has no diarization model and a small bundle; install → download once; enable + process a recording → speakers separated; model reused next run

## 5. Runtime resilience + cleanups

- [x] 5.1 In `lib.rs`, replace the spawn `.expect()` and the unbounded connect-loop with a bounded wait; on timeout or sidecar exit (`CommandEvent::Terminated`), surface an error to the webview and offer retry (re-spawn)
- [x] 5.2 In the React `BackendGate`, cap `/api/status` polling and render an actionable "backend unreachable" view with retry, while still tolerating a slow first-run model download
- [x] 5.3 Report the transcription model state in `/api/status` as loading | ready | failed; record `whisper.load()` failures instead of an indefinite "loading"; surface `failed` + retry in the sidebar/status
- [x] 5.4 Add a rotating file log handler (`data_dir/logs/sirina.log`) alongside stdout in `main.py`; confirm no secrets are written
- [x] 5.5 Add a React error boundary around the routed content; show a recoverable message + reload on a render throw
- [x] 5.6 Add `tauri-plugin-single-instance` (focus the existing window on a second launch); remove the unused `app_password` from `config.py`
- [x] 5.7 Upgrade the startup splash (the `BackendGate` view): branded paper-and-ink screen (logo + serif wordmark, themed, vermilion loading indicator) showing the phase, and hosting the unreachable / model-failure + retry states; respect `prefers-reduced-motion`; works in both the tauri:// and http:// phases

## 6. Startup performance

- [ ] 6.1 Switch `backend/packaging/backend.spec` from onefile to **onedir** (`EXE(exclude_binaries=True)` + `COLLECT(...)`)
- [ ] 6.2 Bundle the onedir `_internal` folder alongside the Tauri sidecar binary so the packaged backend starts (adjust the copy step in `build-macos-app.sh` + Tauri resource bundling); fall back to onefile if onedir proves too fiddly
- [x] 6.3 Defer heavy engine imports out of backend startup so `/api/status` answers in a few seconds and the model loads in the background (sidebar already shows `whisper_state`)

## 7. Verification

- [ ] 7.1 OS permission grant persists across launches/rebuilds with a stable identity; ad-hoc build prints the warning
- [ ] 7.2 Secrets live in the OS keyring (DB fallback when unavailable); existing plaintext secret is migrated and removed from the DB
- [ ] 7.3 Local Ollama honors the configured context window; cloud requests stay OpenAI-compatible (no `num_ctx`)
- [ ] 7.4 Diarization: fresh app has no model + small bundle; install → download once; enable + process → speakers separated; off-by-default path still launches cleanly
- [ ] 7.5 Backend failure (killed sidecar / forced startup error) shows an actionable error + retry, not an endless splash; a second launch focuses the existing window
- [ ] 7.6 Offline first run surfaces a model-unavailable error with retry (not a perpetual "loading"); a forced render error shows the error boundary, not a blank screen
- [ ] 7.7 Startup splash is branded/themed (logo + wordmark), shows the phase, and renders correctly in light and dark
- [ ] 7.8 A rotating log file is written under the data dir with no secrets
- [ ] 7.9 Repeat launches are noticeably faster (no full re-extraction); the app is usable while the model still loads
- [ ] 7.10 `npm run build` and a full `./scripts/build-macos-app.sh` succeed
