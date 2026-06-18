## ADDED Requirements

### Requirement: Settings are persisted and layered over defaults

The system SHALL persist user-edited settings and apply them on top of the built-in defaults and any `.env` configuration, in the order defaults → `.env` → stored overrides. A stored setting MUST take effect without rebuilding the application.

#### Scenario: A changed setting persists across restarts

- **WHEN** the user changes a setting and the app restarts
- **THEN** the changed value is still in effect

#### Scenario: Unset settings fall back

- **WHEN** a setting has no stored override
- **THEN** the effective value comes from `.env` or the built-in default

### Requirement: Settings are read and updated via an API with metadata

The system SHALL expose the current effective settings together with per-field metadata — at minimum the field type, allowed options (for enumerations), whether it is a secret, and whether changing it requires a reload or restart — and SHALL allow updating one or more settings.

#### Scenario: Read settings with metadata

- **WHEN** a client requests the settings
- **THEN** each editable field is returned with its current value and metadata (type, options, secret, restart requirement)

#### Scenario: Update a setting

- **WHEN** a client updates a setting to a valid value
- **THEN** the value is persisted and becomes the effective value

#### Scenario: Invalid value is rejected

- **WHEN** a client updates a setting to a value outside its type/options
- **THEN** the update is rejected and the prior value is retained

### Requirement: Hot settings apply immediately; restart-required settings are marked

Settings that can take effect without reloading models SHALL apply immediately on update. Settings that require reloading the transcription engine or restarting the app SHALL be marked as such, and the system SHALL provide an action to reload the transcription engine.

#### Scenario: Hot setting applies at once

- **WHEN** the user changes a hot setting (e.g. the AI model)
- **THEN** the next operation uses the new value without a restart

#### Scenario: Restart-required setting is flagged

- **WHEN** the user changes a setting that needs the transcription model reloaded (e.g. the whisper model)
- **THEN** the response indicates a reload/restart is required

#### Scenario: Reload the transcription engine when idle

- **WHEN** the user triggers a transcription-engine reload and no recording is being processed
- **THEN** the engine is re-selected and the model reloaded with the new settings

#### Scenario: Reload deferred while busy

- **WHEN** a reload is requested while a recording is being processed
- **THEN** the reload does not proceed and the user is told to wait or restart

### Requirement: Secrets are stored and never returned in plaintext

Secret settings (e.g. tokens and API keys) SHALL be persisted and MUST NOT be returned in plaintext by the settings API; an update with a new value replaces the secret, and an empty update leaves it unchanged.

#### Scenario: Secret is masked on read

- **WHEN** a client reads a secret setting
- **THEN** the response indicates whether a secret is set but does not include its value

#### Scenario: Empty update preserves the secret

- **WHEN** a client updates a secret field with an empty value
- **THEN** the existing secret is preserved

### Requirement: A Settings page exposes the editable settings

The application SHALL provide a Settings page that renders the editable settings grouped into sections (AI model, transcription, speaker diarization, advanced) with appropriate controls, marks fields that require a reload/restart, masks secrets, and shows read-only status (active transcription engine, model loaded, LLM reachable).

#### Scenario: Settings page lists grouped, editable settings

- **WHEN** the user opens the Settings page
- **THEN** editable settings are shown grouped by section with controls matching their type
- **AND** fields requiring a reload/restart are marked
- **AND** read-only status is shown
