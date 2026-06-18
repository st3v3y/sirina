## Context

Every AI feature funnels through `Pipeline` → `self.ollama.generate(prompt) -> str` (3 call sites: `summarize`, `ask`, `cross_ask`). No streaming, no tools. The client is `OllamaClient` (native `/api/generate`, plus the recently-added installed-model fallback). `app-settings` provides a persisted, hot-applying settings store with a secret seam and a registry-driven Settings page. This change makes the *provider* behind that one seam configurable.

## Goals / Non-Goals

**Goals:**
- One provider abstraction covering local (Ollama, LM Studio) and cloud (OpenAI, Google AI Studio, Groq, custom) via the OpenAI-compatible API.
- Dynamic model lists; connection testing; hot-swap on settings change.
- Local-first default; cloud is explicit + disclosed (privacy).

**Non-Goals:**
- Streaming responses or tool/function calling (the seam is prompt→text).
- Per-feature model selection (one global model for now).
- Embeddings / RAG for cross-recording chat (still context-stuffing).
- OS-keyring secret storage (inherited follow-up from `app-settings`).

## Decisions

### 1. One OpenAI-compatible client for everything
Ollama, LM Studio, OpenAI, Google AI Studio, and Groq all expose `POST {base_url}/chat/completions` and `GET {base_url}/models`. So a single `OpenAICompatProvider(base_url, api_key, model)` implements:
- `generate(prompt)` → `POST /chat/completions` `{model, messages:[{role:user, content:prompt}], temperature, stream:false}` → first choice's content.
- `list_models()` → `GET /models` → ids.
- `ping()` → `GET /models` 200.

Presets map a provider key to `(base_url, requires_key, is_cloud)`:

| key       | base_url                                                   | key? | cloud |
| --------- | ---------------------------------------------------------- | ---- | ----- |
| ollama    | http://localhost:11434/v1                                  | no   | no    |
| lmstudio  | http://localhost:1234/v1                                   | no   | no    |
| openai    | https://api.openai.com/v1                                  | yes  | yes   |
| google    | https://generativelanguage.googleapis.com/v1beta/openai   | yes  | yes   |
| groq      | https://api.groq.com/openai/v1                             | yes  | yes   |
| custom    | (user-provided)                                            | maybe| yes*  |

(*custom is treated as cloud/disclosed unless it's an obvious localhost URL.)

*Alternative considered:* separate clients per provider (openai SDK, google SDK). Rejected — more deps, and the OpenAI-compat surface covers our prompt→text need uniformly.

### 2. Settings shape (in the `app-settings` store)
New editable fields registered in the `app-settings` registry (section `ai`, all hot):
- `llm_provider` (enum: the preset keys)
- `llm_model` (string; UI offers a dropdown from discovery)
- `llm_base_url` (string; used/required for `custom`, prefilled from preset otherwise)
- `llm_api_key` (secret)

`runtime.llm` is constructed from these; the `app-settings` PATCH hook for AI fields rebuilds it. The old `ollama_host`/`ollama_model` collapse into `llm_*` (Ollama = the `ollama` preset; host overridable via `llm_base_url`).

### 3. Local model fallback stays — for local only
The installed-model fallback (use an available model if the configured one isn't present) makes sense for Ollama/LM Studio (the user may not have pulled it). For cloud, **do not** auto-substitute — silently switching a billed model is wrong; use the configured model and surface an error if it's invalid. So fallback is gated to local presets.

### 4. Discovery + test endpoints (don't persist)
`POST /api/llm/models` and `POST /api/llm/test` take `{provider, base_url?, api_key?}` and call `list_models()` / `ping()` against a throwaway client — so the UI can populate the model dropdown and verify a key *before* saving. The chosen values are saved through `app-settings` (`PATCH /api/settings`), which is where persistence + the secret seam already live.

### 5. Cloud disclosure is explicit
`GET /api/llm/providers` returns `is_cloud` per preset. The Settings AI section, when a cloud provider is selected, shows a prominent **"Summaries and chat send your meeting transcripts to <provider>."** notice. Local stays the default; nothing leaves the device unless the user picks cloud.

### 6. Status generalization
`/api/status` `ollama_ok`/`model` become `llm_ok`/`llm_provider`/`llm_model` (the whisper `engine` field is unchanged). Existing frontend status usage updates accordingly.

## Risks / Trade-offs

- **Privacy regression** (transcripts to a third party) → Mitigation: opt-in, disclosed, local default; the only path off-device is explicit cloud selection.
- **OpenAI-compat quirks** (Google's endpoint, Groq rate limits, model-id shapes) → Mitigation: the Test action catches misconfig before saving; `custom` base_url escape hatch; keep request to the common subset (messages + temperature, non-streaming).
- **API key handling** → inherits `app-settings` v1 (DB, masked in responses); keyring follow-up.
- **`/models` noise** (OpenAI lists many non-chat models) → Mitigation: show all but allow free-text model entry; optionally filter by name heuristics.
- **Renaming `runtime.ollama` → `runtime.llm`** touches a few sites → Mitigation: mechanical; covered by the existing pipeline tests.

## Migration Plan

1. Add `OpenAICompatProvider` + presets; build `runtime.llm` from settings; point `pipeline` at it.
2. Register `llm_*` fields in the `app-settings` registry; wire the AI-change rebuild hook.
3. Add `/api/llm/providers|models|test`; generalize `/api/status`.
4. Frontend: expand the Settings AI section (provider/model/key/test + cloud warning).
5. Default provider = `ollama`; existing installs behave as today (local Ollama) with no config.
6. Rollback: pin `llm_provider=ollama`; the cloud path is inert.

## Open Questions

- Treat `custom` localhost URLs as local (no warning) by sniffing the host? (Lean: yes — warn only for non-loopback.)
- Persist a tiny per-model param set (temperature/max_tokens) now or later? (Lean: later; keep a sane default.)
- Show which model produced a given summary (provenance) in the UI? (Nice-to-have, later.)
