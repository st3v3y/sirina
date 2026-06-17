## ADDED Requirements

### Requirement: Transcription engine is selected by hardware and availability

The system SHALL select a transcription engine at startup behind a single interface: when configured for automatic selection, it MUST use an Apple-GPU (MLX) engine on Apple Silicon when that engine is available, and otherwise use the CPU faster-whisper engine. Selection MUST be overridable by configuration, and the chosen engine MUST be fixed for the lifetime of the process.

#### Scenario: Apple GPU is used when available

- **WHEN** the app runs on Apple Silicon and the MLX engine is importable and automatic selection is in effect
- **THEN** transcription uses the MLX engine

#### Scenario: Fallback when MLX is unavailable

- **WHEN** the app does not run on Apple Silicon or the MLX engine is unavailable
- **THEN** transcription uses the faster-whisper engine

#### Scenario: Configuration overrides selection

- **WHEN** a specific engine is configured
- **THEN** that engine is used regardless of hardware detection

#### Scenario: Both engines satisfy the same interface

- **WHEN** either engine transcribes a file
- **THEN** it returns transcript lines and a detected/configured language in the same shape
- **AND** downstream diarization and summary stages are unaffected by which engine ran

## MODIFIED Requirements

### Requirement: High-quality offline transcription settings

Transcription SHALL use offline-quality settings rather than the realtime path: a configurable model (defaulting to a quality-oriented model), beam search, voice-activity filtering, and word-level timestamps when needed for speaker alignment. Language SHALL be detected once over the whole file unless a language is configured. Vocabulary hints (`WHISPER_INITIAL_PROMPT`) MUST still be applied where the active engine supports them. These guarantees are engine-independent.

#### Scenario: Whole-file transcription with quality settings

- **WHEN** a recording is transcribed
- **THEN** the whole audio file is processed at once (not in short realtime chunks)
- **AND** word-level timestamps are produced when the track will be diarized, for speaker alignment

#### Scenario: Forced language honored

- **WHEN** a transcription language is configured
- **THEN** detection is skipped and the configured language is used
