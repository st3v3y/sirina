## MODIFIED Requirements

### Requirement: Detail view reflects processing then ready

The recording detail view SHALL show a progress indication while a recording is being transcribed, and SHALL render the stored transcript once the recording is `ready`, without requiring a manual reload. While processing, the indication MUST show the current stage, and a progress bar MUST reflect the completion fraction when one is available (otherwise an indeterminate indicator).

#### Scenario: Progress indication while transcribing

- **WHEN** the user opens a recording whose status is `processing`
- **THEN** the current processing stage is shown
- **AND** a progress bar reflects the completion fraction when available

#### Scenario: Indeterminate when no fraction is available

- **WHEN** the processing stage reports no fraction
- **THEN** an indeterminate progress indicator is shown for that stage

#### Scenario: Transcript appears when ready

- **WHEN** a recording the user is viewing transitions from `processing` to `ready`
- **THEN** the transcript is rendered without a manual page reload

#### Scenario: Failure is surfaced

- **WHEN** a recording's status is `failed`
- **THEN** the detail view shows that transcription failed
