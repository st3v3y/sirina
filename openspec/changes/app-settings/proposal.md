## Why

The packaged desktop app is unconfigurable: every setting is read from `.env`/defaults at build time, so a user can't change the Ollama model, pick a whisper model, set a HuggingFace token, or enable diarization without editing files or rebuilding. A double-click app needs an in-app **Settings page** backed by a writable store.

## What Changes

- **DB-backed settings store**: a `Setting` key/value table; effective config is layered **defaults → `.env` → DB overrides**. Changing a setting persists to the DB and updates the running config.
- **Settings API**: `GET /api/settings` (current effective values + per-field metadata: type, options, whether a restart/reload is required, secret-or-not with masking) and `PATCH /api/settings` (update one or more keys; applies hot changes immediately).
- **Hot vs restart-required**: hot settings (LLM model/host, language, vocabulary hints, chunk/silence, diarization toggle + HF token) take effect immediately; restart-required settings (whisper model, transcription engine, compute type, cpu threads) are marked, with an in-app **"Reload transcription engine"** action (and a clear restart note if a job is in flight).
- **Settings page** with sections: **AI model** (Ollama host + model picked from installed models — the full provider picker comes in `dynamic-llm-provider`), **Transcription** (engine, model, language, vocabulary hints), **Speaker diarization** (enable + HF token + model), **Advanced** (chunk seconds, silence threshold, cpu threads, data-folder path + "open in Finder"), and read-only **Status** (active engine, whisper loaded, Ollama reachable).
- **Secrets**: stored in the settings store for v1 (local, single-user machine), returned masked. A cross-platform OS keyring (macOS Keychain / Windows Credential Manager / Linux Secret Service, via the `keyring` library, DB fallback) is noted as a follow-up.

## Capabilities

### New Capabilities

- `app-settings`: A persistent, user-editable settings store (layered config), a read/update API with per-field metadata (restart-required, secret), and a Settings UI page; plus a reload-transcription-engine action for restart-required changes.

### Modified Capabilities

_None — additive. Existing transcription/diarization/LLM behavior is unchanged; it simply reads config that may now carry DB overrides._

## Impact

- **Backend**:
  - `models.py`: a `Setting` table (key, value).
  - A settings service that, at startup, applies DB overrides onto the singleton `Settings` object (so existing `settings.X` read sites need no change) and re-applies on update; a registry of editable fields with metadata (type/options/restart/secret).
  - New `api/settings.py`: `GET`/`PATCH /api/settings`; `POST /api/settings/reload-engine` (re-select + reload whisper when idle).
  - On LLM-setting change, rebuild `runtime.ollama`; on whisper/engine change, flag reload-required.
- **Frontend**:
  - New `pages/Settings.tsx` + `/settings` route and nav entry; `lib/api.ts` settings wrappers.
  - Fields render from the API metadata (restart badges, masked secrets, model dropdown from installed Ollama models / `/api/audio` style helpers).
- **DB**: one additive `setting` table (created by `create_all`); no migration of existing data.
- **Depends-on / enables**: `dynamic-llm-provider` builds its provider/key/model fields on this store. Diarization in the packaged app still requires the `backend.spec` bundling change (sequenced separately); the toggle is exposed but no-ops until pyannote is bundled.
