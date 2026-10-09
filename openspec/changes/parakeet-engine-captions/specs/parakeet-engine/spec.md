## ADDED Requirements

### Requirement: Parakeet engine transcribes on any hardware

The system SHALL provide a `parakeet` transcription engine that runs NVIDIA Parakeet TDT 0.6B v3 (int8) on the CPU through sherpa-onnx, inside the backend process, on macOS, Windows and Linux. It MUST satisfy the common engine interface. For each window, it returns transcript lines with absolute segment and word timestamps. Speech regions are found with voice-activity detection, so silence yields no text.

#### Scenario: Window transcription with word timings

- **WHEN** the Parakeet engine transcribes the window `[T, T+180)` of a track
- **THEN** it returns lines whose segment and word times fall within the window and are offset by T
- **AND** each line carries word-level timings usable by speaker splitting

#### Scenario: No GPU required

- **WHEN** the app runs on a machine without a supported GPU
- **THEN** the Parakeet engine loads and transcribes on the CPU

#### Scenario: Silence produces nothing

- **WHEN** a window contains no speech
- **THEN** the engine returns no lines for it

### Requirement: Parakeet language coverage is explicit

The Parakeet engine SHALL be treated as supporting exactly these languages: Bulgarian, Croatian, Czech, Danish, Dutch, English, Estonian, Finnish, French, German, Greek, Hungarian, Italian, Latvian, Lithuanian, Maltese, Polish, Portuguese, Romanian, Russian, Slovak, Slovenian, Spanish, Swedish and Ukrainian. The language within that set is detected automatically. Because the engine does not report the detected language, a recording transcribed by Parakeet MUST store the configured language when one is set, and no language otherwise.

#### Scenario: Configured language is stored

- **WHEN** a recording is transcribed by Parakeet with the language setting `de`
- **THEN** the recording's language is stored as `de`

#### Scenario: Auto-detect leaves language empty

- **WHEN** a recording is transcribed by Parakeet with no language configured
- **THEN** the recording has no stored language and the language badge is not shown

### Requirement: Vocabulary hints are honoured or declared unsupported

When the vocabulary-hint setting is non-empty, the Parakeet engine SHALL pass the hints to the recognizer as hotwords if the bundled sherpa-onnx supports contextual biasing for the Parakeet model. If it does not, the Settings page MUST state that vocabulary hints apply only to the Whisper engines while Parakeet is active.

#### Scenario: Hints shown as Whisper-only

- **WHEN** Parakeet is the active engine and hotwords are not supported for it
- **THEN** the vocabulary-hints setting shows that it applies to Whisper engines only

### Requirement: Parakeet models are managed on demand

The Parakeet model SHALL be listed in the model manager with name, size and install status. If the caption worker needs a separate voice-activity model, that model SHALL be listed too. These models MUST be downloaded on first use or on install and never bundled, and they MUST follow the existing install, delete and recoverable-failure rules for speech models. Final transcription MUST reuse the voice-activity model already bundled with the app.

#### Scenario: First use downloads the model

- **WHEN** Parakeet is the selected engine and its model is not installed
- **THEN** the Parakeet model is downloaded into the data directory, with download progress shown
- **AND** transcription proceeds once both are installed

#### Scenario: Download fails

- **WHEN** the Parakeet download fails and the faster-whisper model is installed
- **THEN** the job falls back to faster-whisper with a note, and the model manager offers a retry

### Requirement: Parakeet caption worker meets near-real-time targets

When Parakeet captions ship on a platform, the caption worker SHALL run as a separate process using the same stdin-PCM / stdout-JSON caption protocol as the macOS speech helper. It emits provisional lines while a phrase is spoken and settled lines when it ends. A phrase that runs longer than a maximum segment length (default 15 s) MUST be settled at that length, so captions keep flowing during monologues.

#### Scenario: Provisional then settled lines

- **WHEN** a speaker says a phrase during a recording with Parakeet captions on
- **THEN** a provisional line appears within 2 seconds of the speech and is updated while it continues
- **AND** a settled line replaces it within 3 seconds of the phrase ending

#### Scenario: Long monologue

- **WHEN** a speaker talks for 40 seconds without a pause
- **THEN** settled lines are emitted at most every 15 seconds rather than one line at the end
