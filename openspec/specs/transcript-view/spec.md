# transcript-view Specification

## Purpose
TBD - created by archiving change offline-transcription. Update Purpose after archive.
## Requirements
### Requirement: Detail view reflects processing then ready

The recording detail view SHALL show a processing indication while a recording is being transcribed, and SHALL render the stored transcript once the recording is `ready`, without requiring a manual reload.

#### Scenario: Processing indication while transcribing

- **WHEN** the user opens a recording whose status is `processing`
- **THEN** a processing indication is shown instead of a transcript

#### Scenario: Transcript appears when ready

- **WHEN** a recording the user is viewing transitions from `processing` to `ready`
- **THEN** the transcript is rendered without a manual page reload

#### Scenario: Failure is surfaced

- **WHEN** a recording's status is `failed`
- **THEN** the detail view shows that transcription failed

