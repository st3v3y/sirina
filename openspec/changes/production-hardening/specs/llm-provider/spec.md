## ADDED Requirements

### Requirement: Local providers honor a configured context window

For local providers (e.g. Ollama), the system SHALL apply the configured context-window setting to the model's runtime context so the full prompt is processed rather than silently truncated to the provider's default. Cloud providers, which already honor their model's context, MUST NOT receive a local-only context parameter.

#### Scenario: Local request uses the configured context

- **WHEN** a local provider generates a completion and a context-window size is configured
- **THEN** the request sets the model's runtime context to at least that size

#### Scenario: Cloud providers are unaffected

- **WHEN** a cloud provider generates a completion
- **THEN** no local-only context parameter is sent and the request stays OpenAI-compatible
