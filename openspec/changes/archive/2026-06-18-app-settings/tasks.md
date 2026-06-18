## 1. Backend — settings store

- [x] 1.1 Add a `Setting` table (key TEXT primary key, value TEXT) to `models.py`
- [x] 1.2 Add an editable-field registry (key → label, section, type, options, secret, restart) as the single source of truth for editable settings
- [x] 1.3 Add a settings service: load DB rows at startup and `setattr` coerced values onto the `Settings` singleton; `apply(updates)` validates against the registry, persists, and `setattr`s
- [x] 1.4 Route secrets through a `secret_get/secret_set` seam (DB-backed in v1) so a `keyring` backend can replace it later without touching call sites

## 2. Backend — settings API

- [x] 2.1 `GET /api/settings`: return each editable field's effective value (secrets masked) + metadata (type/options/secret/restart)
- [x] 2.2 `PATCH /api/settings`: validate + persist + apply; reject unknown keys / invalid values per field; empty secret leaves it unchanged
- [x] 2.3 On LLM-setting change, rebuild `runtime.ollama`; on whisper/engine/compute/threads change, flag `reload_required` in the response
- [x] 2.4 `POST /api/settings/reload-engine`: re-run `select_engine()` + `whisper.load()` only when no job is processing; otherwise return busy
- [x] 2.5 Register the settings router and call the startup loader after `init_db()`

## 3. Frontend — Settings page

- [x] 3.1 `lib/api.ts`: `getSettings()`, `updateSettings(patch)`, `reloadEngine()` + types
- [x] 3.2 `pages/Settings.tsx` rendering fields from the API metadata, grouped by section, with per-type controls (text/number/toggle/dropdown)
- [x] 3.3 Mark reload/restart-required fields; mask secrets (show "set", edit replaces); show a "Reload transcription engine" button (+ busy/restart note)
- [x] 3.4 AI section: Ollama host + model dropdown populated from installed models; Transcription: engine/model/language/vocabulary; Diarization: enable + HF token (+ "not available in this build" note); Advanced: chunk/silence/cpu-threads + data-folder path
- [x] 3.5 Read-only Status block (active engine, whisper loaded, Ollama reachable) reusing `/api/status`
- [x] 3.6 Add `/settings` route + nav entry in `App.tsx`

## 4. Verification

- [x] 4.1 Change the Ollama model in Settings → the next summary uses it without a restart
- [x] 4.2 Change the whisper model → field is flagged reload-required; "Reload transcription engine" applies it when idle; busy while processing
- [x] 4.3 Set the HF token (secret) → stored, returned masked; empty update preserves it
- [x] 4.4 Settings persist across an app restart; absent overrides fall back to `.env`/defaults (unchanged behavior on a fresh install)
- [x] 4.5 Invalid value (e.g. bad enum) is rejected and the prior value retained
- [x] 4.6 Status block reflects the active engine / whisper-loaded / Ollama-reachable state
