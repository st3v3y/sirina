## MODIFIED Requirements

### Requirement: A Settings page exposes the editable settings

The application SHALL provide a Settings page that renders the editable settings grouped into sections (AI model, transcription, live captions, speech models, speaker splitting, advanced) with appropriate controls, marks fields that require a reload/restart, masks secrets, and shows read-only status (active transcription engine and, when it differs from the configured one, why; model loaded; LLM reachable; caption support).

#### Scenario: Settings page lists grouped, editable settings

- **WHEN** the user opens the Settings page
- **THEN** editable settings are shown grouped by section with controls matching their type
- **AND** fields requiring a reload/restart are marked
- **AND** read-only status is shown

#### Scenario: Engine fallback is explained

- **WHEN** the configured engine is WhisperKit but faster-whisper is active
- **THEN** the transcription section states the reason (e.g. helper missing, model not installed)

## ADDED Requirements

### Requirement: Transcription speed settings

The settings SHALL include: the transcription engine (auto, WhisperKit, faster-whisper), the live-captions default, the transcribe-during-recording default, when speakers are split (after the recording by default, or also during it), and the final-pass window length. The diarization access-token field is removed. The CPU thread count setting MUST default to "auto" (performance cores). Changing the engine MUST follow the existing reload-when-idle rule. (WhisperKit has a single model, large-v3-turbo 626 MB, so there is no WhisperKit model setting.)

#### Scenario: Toggle captions

- **WHEN** the user enables live captions on a supported Mac
- **THEN** the next recording shows captions without restarting the app

#### Scenario: Change engine while busy

- **WHEN** the user changes the engine while a job runs
- **THEN** the change is saved and applied when the job finishes
