# processing-progress Specification

## Purpose
TBD - created by archiving change processing-progress-and-mlx-whisper. Update Purpose after archive.
## Requirements
### Requirement: Post-recording processing reports staged progress

While a recording is being processed, the system SHALL track its progress as a stage (`queued`, `preparing_model`, `drafting`, `transcribing`, `diarizing`, `summarizing`, `compressing`, `done`) and, where the stage supports it, a completion fraction between 0 and 1. `preparing_model` covers a first-time model download or Neural Engine preparation; `drafting` covers the fast draft pass. This progress MUST be exposed to clients for the in-flight recording.

#### Scenario: Stage advances through processing

- **WHEN** a recording moves through drafting, transcription, diarization, and summary generation
- **THEN** its reported stage advances accordingly
- **AND** clients can read the current stage for that recording

#### Scenario: First-time model preparation is visible

- **WHEN** the WhisperKit model must be downloaded or prepared before the first window
- **THEN** the stage is `preparing_model` with an explanation that this happens once

#### Scenario: Transcription reports a fraction when available

- **WHEN** the active transcription engine processes audio incrementally
- **THEN** the transcription stage reports a fraction derived from processed audio time over total audio duration

#### Scenario: Stage-only when no fraction is available

- **WHEN** a stage (e.g. diarization or summary) or an engine cannot report a fraction
- **THEN** the stage is reported without a real fraction

### Requirement: Progress includes elapsed time and a time-based estimate

Progress SHALL include the elapsed time since processing started. For a non-streaming engine that cannot report a real fraction, the system SHALL derive a time-based estimated fraction from elapsed time against an estimate of the work, capped below 1.0, and flag it as estimated so the UI can distinguish it from a measured fraction.

#### Scenario: Elapsed time is reported while processing

- **WHEN** a recording is being processed
- **THEN** the reported progress includes the seconds elapsed since it started

#### Scenario: Estimated fraction for a non-streaming engine

- **WHEN** the active engine cannot report a real fraction and the audio duration is known
- **THEN** progress reports an estimated fraction derived from elapsed time, marked as estimated, never reaching 1.0 before completion

### Requirement: Progress is ephemeral and per-recording

Processing progress SHALL be held in memory per recording and MUST NOT be persisted to the database. Progress for a recording that is not currently processing MAY be absent.

#### Scenario: No progress for idle recordings

- **WHEN** a recording is `ready` or `failed`
- **THEN** no live progress is reported for it

#### Scenario: Progress does not survive as stored data

- **WHEN** the backend restarts
- **THEN** progress is reconstructed from re-processing, not loaded from storage

### Requirement: Progress reports the final-transcript boundary

While the final transcription pass runs, progress SHALL include `final_until_s` as stored on the recording: the time up to which the transcript is final. It MUST be absent when no final window has committed yet, and MUST equal the recording duration when the pass completes.

#### Scenario: Boundary reported per window

- **WHEN** a final window ending at 380 s commits
- **THEN** progress for that recording reports `final_until_s` = 380

### Requirement: Progress explains slow power states

When processing runs while the Mac is on battery or in Low Power Mode, progress SHALL include a power note that names the condition and that transcription is slower in it. The note MUST disappear when the condition ends.

#### Scenario: Low Power Mode note

- **WHEN** a recording is processing and Low Power Mode is on
- **THEN** progress includes a note that Low Power Mode slows transcription

#### Scenario: Plugged in again

- **WHEN** the Mac returns to AC power with Low Power Mode off during processing
- **THEN** the power note is no longer reported

