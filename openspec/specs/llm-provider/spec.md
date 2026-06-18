# llm-provider Specification

## Purpose
TBD - created by archiving change dynamic-llm-provider. Update Purpose after archive.
## Requirements
### Requirement: Pluggable LLM provider behind one interface

All AI features (summaries, per-recording Q&A, cross-recording chat) SHALL obtain text completions through a single provider interface (prompt in, text out), and the active provider MUST be selectable without changing that feature code. Local providers (Ollama, LM Studio) and cloud providers (OpenAI, Google AI Studio, Groq, and a custom OpenAI-compatible endpoint) SHALL be supported through one OpenAI-compatible client distinguished by base URL, key requirement, and model.

#### Scenario: Switching provider does not change feature behavior

- **WHEN** the active LLM provider is changed
- **THEN** summaries, Q&A, and chat use the new provider
- **AND** no feature-specific code changes are required

#### Scenario: A cloud provider needs a key, a local one does not

- **WHEN** a cloud provider (e.g. OpenAI) is selected
- **THEN** an API key is required
- **AND** when a local provider (Ollama/LM Studio) is selected, no key is required

### Requirement: Models are discovered dynamically

The system SHALL discover the available models for the selected provider — installed models for a local provider, and the provider's model listing for a cloud provider — so the user picks from real options. It SHALL also let the user verify connectivity before saving.

#### Scenario: Local model list

- **WHEN** a local provider is selected
- **THEN** the model options are that provider's installed models

#### Scenario: Cloud model list with a key

- **WHEN** a cloud provider is selected and a valid API key is supplied
- **THEN** the model options are fetched from the provider's model listing

#### Scenario: Connection test before saving

- **WHEN** the user tests a provider/key/model combination
- **THEN** the system reports whether the provider is reachable, without persisting the values

### Requirement: Local model fallback only for local providers

When the configured model is not available, the system SHALL fall back to an installed model for local providers, but MUST NOT auto-substitute a different model for cloud providers (to avoid silently using an unintended billed model).

#### Scenario: Local fallback

- **WHEN** a local provider's configured model is not installed
- **THEN** an available installed model is used and a warning is logged

#### Scenario: Cloud does not substitute

- **WHEN** a cloud provider's configured model is invalid
- **THEN** the call fails and surfaces an error rather than substituting another model

### Requirement: Cloud use is opt-in and disclosed

A cloud provider SHALL be chosen explicitly by the user, and the UI SHALL clearly disclose that selecting it sends meeting transcripts to that provider. The default provider MUST be local.

#### Scenario: Cloud selection shows a disclosure

- **WHEN** the user selects a cloud provider
- **THEN** the UI shows that transcripts will be sent to that provider

#### Scenario: Default is local

- **WHEN** the app runs with no LLM provider configured
- **THEN** the active provider is a local one and no data leaves the device

