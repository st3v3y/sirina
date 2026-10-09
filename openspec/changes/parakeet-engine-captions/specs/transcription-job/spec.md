## MODIFIED Requirements

### Requirement: Transcription engine is selected by hardware and availability

The system SHALL select a final transcription engine at startup behind a single interface. When configured for automatic selection, it MUST:
1. use the native WhisperKit engine on Apple Silicon when the bundled speech helper is present and its configured model is installed (or downloadable);
2. otherwise, use the Parakeet engine, unless the configured language is outside Parakeet's supported languages;
3. otherwise, use the faster-whisper engine.

The MLX engine MUST NOT be chosen by automatic selection. Selection MUST be overridable by configuration (`whisperkit`, `parakeet`, `faster-whisper`). The chosen engine MUST be fixed for the lifetime of the process, until an explicit engine reload.

#### Scenario: WhisperKit is used when available

- **WHEN** the app runs on Apple Silicon, the speech helper is bundled, the WhisperKit model is installed, and automatic selection is in effect
- **THEN** transcription uses the WhisperKit engine

#### Scenario: Parakeet is the default elsewhere

- **WHEN** automatic selection is in effect on Windows or Linux and no language, or a Parakeet-supported language, is configured
- **THEN** transcription uses the Parakeet engine

#### Scenario: Unsupported language falls back to faster-whisper

- **WHEN** automatic selection is in effect, WhisperKit is unavailable, and the configured language is not supported by Parakeet (e.g. `ja`)
- **THEN** transcription uses the faster-whisper engine
- **AND** the reason is recorded so Settings can show it

#### Scenario: Fallback when the chosen engine is unavailable

- **WHEN** the selected engine cannot start (WhisperKit helper missing or failing, or the Parakeet runtime failing to load)
- **THEN** transcription uses the next engine in the automatic order that can start, ending with faster-whisper
- **AND** the reason for the fallback is recorded so Settings can show it

#### Scenario: Configuration overrides selection

- **WHEN** a specific engine is configured
- **THEN** that engine is used regardless of hardware detection, falling back to faster-whisper only if the configured engine cannot start

#### Scenario: Engines satisfy the same interface

- **WHEN** any engine transcribes a window of a track
- **THEN** it returns transcript lines with word timestamps and a detected/configured language (or none) in the same shape
- **AND** downstream diarization and summary stages are unaffected by which engine ran
