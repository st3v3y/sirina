# transcription-job Specification

## Purpose
TBD - created by archiving change offline-transcription. Update Purpose after archive.
## Requirements
### Requirement: Transcription runs after a recording stops

When a recording is stopped (status `processing`), the system SHALL transcribe its audio in the background and, on success, persist the transcript and set the recording status to `ready`.

#### Scenario: Stopped recording becomes ready with a transcript

- **WHEN** a recording is stopped and its audio contains speech
- **THEN** the system transcribes the audio and stores `Segment` rows with start time, end time, and text
- **AND** the recording status becomes `ready`

#### Scenario: Transcription failure is recorded

- **WHEN** transcription of a recording raises an error
- **THEN** the recording status becomes `failed`
- **AND** an error message is stored on the recording

### Requirement: One job at a time, restart-safe

Transcription jobs SHALL run one at a time through a queue. On startup, any recording left in `processing` (e.g. due to a crash or restart) MUST be re-enqueued.

#### Scenario: Jobs do not run concurrently

- **WHEN** two recordings are stopped in quick succession
- **THEN** their transcription jobs run sequentially, not simultaneously

#### Scenario: Pending recordings resume after restart

- **WHEN** the backend starts and a recording is in `processing` with no transcript
- **THEN** that recording is re-enqueued for transcription

### Requirement: High-quality offline transcription settings

Transcription SHALL use offline-quality settings rather than the realtime path: a configurable model (defaulting to a quality-oriented model), beam search, voice-activity filtering, and word-level timestamps. Language SHALL be detected once over the whole file unless a language is configured. Vocabulary hints (`WHISPER_INITIAL_PROMPT`) MUST still be applied.

#### Scenario: Whole-file transcription with quality settings

- **WHEN** a recording is transcribed
- **THEN** the whole audio file is processed at once (not in short realtime chunks)
- **AND** word-level timestamps are produced for later speaker alignment

#### Scenario: Forced language honored

- **WHEN** a transcription language is configured
- **THEN** detection is skipped and the configured language is used

### Requirement: Detected language is stored

The detected (or configured) language of a recording SHALL be stored on the recording.

#### Scenario: Language persisted on completion

- **WHEN** a recording finishes transcription
- **THEN** its language code is stored on the recording

