## Context

All config lives in a pydantic-settings `Settings` singleton (`app/config.py`), read at startup from defaults + `.env` (and, since the desktop work, `APP_DATA_DIR/.env`). Read sites everywhere do `settings.whisper_model`, `settings.ollama_model`, etc. There is no persistence the UI can write and no Settings page. The transcription engine + whisper model are loaded once at startup (`select_engine()`, `whisper.load()`); the LLM client (`runtime.ollama`) is built once; diarization reads `settings` lazily when the diarizer loads.

## Goals / Non-Goals

**Goals:**
- A user-editable, persisted settings store the Settings page reads/writes.
- Make hot settings take effect immediately; clearly mark restart-required ones and offer an in-app reload for the transcription engine.
- Keep the existing `settings.X` read sites working unchanged.
- Local-first; no behavior change unless the user edits a setting.

**Non-Goals:**
- The full multi-provider LLM picker (that's `dynamic-llm-provider`; this ships a basic Ollama host+model field).
- OS keyring secret storage (follow-up; v1 stores secrets in the DB).
- Bundling pyannote/torch so diarization actually runs in the packaged app (sequenced separately; the toggle is exposed but inert until then).
- Per-feature model selection.

## Decisions

### 1. Layer DB overrides onto the existing `Settings` singleton
Add a `Setting(key, value)` table. At startup, after `init_db()`, load all rows and `setattr(settings, key, coerce(value))` for known editable keys — so every existing `settings.X` read transparently sees overrides. On `PATCH /api/settings`, persist to the DB and `setattr` again.
- *Why mutate the singleton* instead of an accessor layer: zero churn at the ~dozens of read sites, and pydantic v2 model instances are mutable by default. We validate/coerce on write.
- *Coercion*: values stored as text; cast to the field's type from the editable-field registry (below).

### 2. An editable-field registry (single source of truth for the UI)
A table of editable settings, each with: `key`, `label`, `section` (ai | transcription | diarization | advanced), `type` (string | int | float | bool | enum), `options` (for enums, e.g. engine/model/language), `secret` (bool), `restart` (none | reload_engine | restart_app). `GET /api/settings` returns the current effective value + this metadata per field; the page renders entirely from it (so adding a field later — e.g. the LLM provider — is a registry edit, not bespoke UI).
- Secrets are returned masked (e.g. `"set"` / `""`), never the plaintext; a PATCH with a new value replaces it, an empty value leaves it unchanged.

### 3. Applying changes — hot vs restart
On PATCH, group by effect:
- **hot** (llm host/model, language, initial_prompt, beam_size, chunk_seconds, silence_threshold, diarization_enabled, hf_token): just `setattr`; read fresh on next use. For the LLM, rebuild `runtime.ollama` so a model/host change applies to the next summary.
- **reload_engine** (whisper_model, transcription_engine, compute_type, cpu_threads): `setattr` + flag `reload_required`. The response says a reload is needed; the user triggers `POST /api/settings/reload-engine`.
- The reload action re-runs `select_engine()` + `whisper.load()` **only when no job is processing**; if a job is in flight it returns "busy — finish or restart". This avoids swapping the model mid-transcription. A plain app restart is always a valid fallback (documented).

### 4. Secrets storage (v1) + cross-platform keyring follow-up
v1: secrets (HF token; later LLM API keys) live in the `setting` table as plaintext — acceptable for a local, single-user app on the user's own machine; the file is already under their home dir. Follow-up: store secrets via the `keyring` library, which maps to **macOS Keychain**, **Windows Credential Manager**, and **Linux Secret Service** (GNOME Keyring/KWallet), with the DB as the fallback when no OS backend exists. The store interface is written so secrets route through a `secret_get/secret_set` seam, making the keyring swap a localized change.

### 5. Settings page renders from metadata
`Settings.tsx` fetches `GET /api/settings`, groups fields by section, renders the right control per `type` (text / number / toggle / dropdown), shows a "needs restart" / "reload engine" badge where `restart != none`, masks secrets, and surfaces a "Reload transcription engine" button + the read-only Status block (reusing `/api/status`). The Ollama model dropdown is populated from the installed-models list.

## Risks / Trade-offs

- **Mutating the singleton** → a bad value could break reads. → Mitigation: validate/coerce against the registry on write; reject unknown keys; keep `.env`/defaults as the floor.
- **Reload mid-job** → model swap could corrupt an in-flight transcription. → Mitigation: only reload when idle; else instruct to wait/restart.
- **Plaintext secrets** → readable on disk. → Mitigation: documented v1 trade-off for a local app; keyring follow-up; mask in API responses.
- **Settings drift between `.env` and DB** → confusing precedence. → Mitigation: fixed, documented order (defaults → .env → DB); the page shows the effective value.
- **Diarization toggle is inert in the packaged app** (pyannote not bundled) → user confusion. → Mitigation: show a "not available in this build" note next to the toggle until bundling lands.

## Migration Plan

1. Add the `setting` table (create_all) + the settings service (load-on-startup, apply-on-PATCH) + editable-field registry.
2. Add `api/settings.py` (GET/PATCH + reload-engine).
3. Frontend Settings page + route + nav + api wrappers.
4. No data migration; absent rows = defaults/.env, so existing installs behave identically until a user changes something.
5. Rollback: ignore the table; config falls back to defaults/.env.

## Open Questions

- Should restart-required changes auto-offer the reload, or always require the explicit button? (Lean: explicit button, since reload is only safe when idle.)
- Do we expose `ollama_host` in the basic AI section now, or wait for `dynamic-llm-provider`? (Lean: expose host + model now; it's immediately useful.)
- Where to surface validation errors (per-field vs a banner)? (Lean: per-field.)
