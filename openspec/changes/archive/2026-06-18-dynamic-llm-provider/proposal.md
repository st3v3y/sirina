## Why

The app only talks to Ollama, and only via the default model. A local 3B model is fine for quick notes but weak for real summaries and cross-recording chat. Users should be able to choose a better model — including their own cloud account (OpenAI, **Google AI Studio**, Groq) — while keeping the app **local-first and private by default**. Because every AI feature already funnels through one seam (`generate(prompt) -> str`), the provider can be made pluggable without touching the summary/Q&A/chat logic.

## What Changes

- **One pluggable LLM provider** behind the existing `generate(prompt) -> str` seam. Local providers (**Ollama**, **LM Studio**) and cloud providers (**OpenAI**, **Google AI Studio**, **Groq**, **Custom**) are unified by a single **OpenAI-compatible** client — they differ only by base URL, whether a key is required, and the model.
- **Provider + model pickers**: a provider dropdown and a model dropdown whose options are **fetched dynamically** — installed models for Ollama/LM Studio, the provider's `/models` endpoint for cloud. An API-key field appears for cloud, plus a **Test connection** action.
- **Local-first, cloud opt-in + disclosed**: the default is a local provider; selecting a cloud provider shows a clear **"transcripts will be sent to <provider>"** warning, because choosing cloud means meeting transcripts leave the device.
- **Hot-swappable**: changing the provider/model/key applies to the next summary/answer without a restart (it's a hot setting in the `app-settings` store).
- **One global model** for all AI features (summaries, per-recording Q&A, cross-recording chat) — per-feature models are a later option.

## Capabilities

### New Capabilities

- `llm-provider`: A pluggable, OpenAI-compatible LLM provider with local (Ollama/LM Studio) and opt-in cloud (OpenAI/Google AI Studio/Groq/custom) presets, dynamic model discovery, connection testing, and cloud-disclosure.

### Modified Capabilities

- `local-only-runtime`: Add a requirement that inference is **local by default** and any cloud provider is **opt-in and disclosed** (transcripts leaving the device). Status additionally reports the active LLM provider/model.

## Impact

- **Backend**:
  - `llm/`: a single `OpenAICompatProvider` (`generate`, `list_models`, `ping`) + a preset table (base_url, requires_key, is_cloud). Replaces direct `OllamaClient` use; Ollama/LM Studio are just local presets. Keep the installed-model fallback for local providers; cloud uses the configured model as-is.
  - `runtime.llm` built from settings; rebuilt on an LLM-setting change (via the `app-settings` PATCH hook). `pipeline.py` calls `runtime.llm.generate` (rename from `runtime.ollama`).
  - API: `GET /api/llm/providers` (presets + is_cloud/requires_key); `POST /api/llm/models` and `POST /api/llm/test` (given provider/base_url/api_key, list models / verify reachability). The chosen provider/model/key persist through `app-settings`.
  - `api/status.py`: report `llm_provider` / `llm_model` (generalize the current `ollama_ok`/`model`).
- **Frontend**: extend the Settings page **AI model** section — provider dropdown, conditional API-key field, model dropdown (dynamic), Test button, and the cloud "leaves your device" warning.
- **Settings**: provider/model/base_url/api_key live in the `app-settings` store; the API key is a secret (DB in v1, keyring follow-up).
- **Depends-on**: `app-settings` (the store, the secret seam, the registry-driven Settings page). No DB schema change beyond the settings already added there.
- **Privacy**: the only change that lets data leave the machine — gated behind explicit cloud selection + disclosure; local remains the default.
