## 1. Backend — provider abstraction

- [ ] 1.1 Add `OpenAICompatProvider(base_url, api_key, model)` in `llm/`: `generate(prompt)` (POST /chat/completions, non-stream), `list_models()` (GET /models), `ping()`
- [ ] 1.2 Add a provider preset table: ollama, lmstudio, openai, google, groq, custom → (base_url, requires_key, is_cloud)
- [ ] 1.3 Keep the installed-model fallback but gate it to local providers; cloud uses the configured model as-is (error if invalid)
- [ ] 1.4 Build `runtime.llm` from settings; rename `runtime.ollama` → `runtime.llm` and point `pipeline.py` (summarize/ask/cross_ask) at it
- [ ] 1.5 Rebuild `runtime.llm` when an AI setting changes (hook into the `app-settings` PATCH apply path)

## 2. Backend — settings + API

- [ ] 2.1 Register `llm_provider` (enum), `llm_model`, `llm_base_url`, `llm_api_key` (secret) in the `app-settings` registry (section `ai`, hot); default `llm_provider=ollama`
- [ ] 2.2 `GET /api/llm/providers` → presets with `is_cloud` / `requires_key` / default base_url
- [ ] 2.3 `POST /api/llm/models` and `POST /api/llm/test` (provider/base_url/api_key) → list models / verify reachability against a throwaway client; do not persist
- [ ] 2.4 Generalize `/api/status`: `llm_ok` + `llm_provider` + `llm_model` (keep the whisper `engine` field)

## 3. Frontend — Settings AI section

- [ ] 3.1 `lib/api.ts`: `getLlmProviders()`, `listLlmModels(cfg)`, `testLlm(cfg)` + types; update `Status` type
- [ ] 3.2 Provider dropdown; conditional API-key field for cloud; base_url field for custom
- [ ] 3.3 Model dropdown populated dynamically (local installed models / cloud /models); allow free-text fallback
- [ ] 3.4 "Test connection" button with result; save via the existing settings PATCH
- [ ] 3.5 Cloud disclosure: prominent "transcripts will be sent to <provider>" notice when a cloud provider is selected; local stays default
- [ ] 3.6 Update any status display that referenced `ollama_ok`/`model`

## 4. Verification

- [ ] 4.1 Default (Ollama) works unchanged; a summary uses the local model
- [ ] 4.2 Switch provider/model in Settings → next summary/Q&A/chat uses it, no restart
- [ ] 4.3 Select a cloud provider + key → model dropdown populates from /models; Test reports reachable; a summary uses the cloud model
- [ ] 4.4 Cloud selection shows the "leaves your device" disclosure; switching back to local clears it
- [ ] 4.5 Local fallback still substitutes an installed model; cloud does NOT substitute (invalid model errors)
- [ ] 4.6 `/api/status` reports the active provider/model
