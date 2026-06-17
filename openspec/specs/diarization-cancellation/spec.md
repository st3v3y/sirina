# diarization-cancellation Specification

## Purpose
TBD - created by archiving change chunked-transcription-and-early-transcript. Update Purpose after archive.
## Requirements
### Requirement: Diarization can be cancelled, summary still runs

While a recording's diarization stage is in progress, the system SHALL allow the user to cancel it. On cancellation, the system MUST fall back to the baseline speaker split for the already-transcribed lines and MUST still generate the summary, completing the recording.

#### Scenario: Cancel during diarization falls back to baseline

- **WHEN** the user cancels diarization while it is the active stage
- **THEN** the recording's speakers are the baseline split (e.g. "You"/"Others"/"Speaker 1")
- **AND** the transcript text is preserved
- **AND** the summary is still generated and the recording becomes `ready`

#### Scenario: Cancel is a no-op when not diarizing

- **WHEN** a cancel request arrives and the recording is not in the diarizing stage
- **THEN** the request has no effect and the recording continues normally

#### Scenario: Cancel control is shown only while diarizing

- **WHEN** a recording's processing stage is `diarizing`
- **THEN** a cancel control is available to the user
- **AND** it is not shown during other stages

