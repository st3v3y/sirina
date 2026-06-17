## ADDED Requirements

### Requirement: Post-recording processing reports staged progress

While a recording is being processed, the system SHALL track its progress as a stage (`queued`, `transcribing`, `diarizing`, `summarizing`, `done`) and, where the stage supports it, a completion fraction between 0 and 1. This progress MUST be exposed to clients for the in-flight recording.

#### Scenario: Stage advances through processing

- **WHEN** a recording moves through transcription, diarization, and summary generation
- **THEN** its reported stage advances accordingly
- **AND** clients can read the current stage for that recording

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
