## ADDED Requirements

### Requirement: Transcript renders progressively while processing

The recording detail view SHALL render transcript segments as soon as they are available, while the recording is still `processing`, rather than only after it becomes `ready`. The progress indication for the remaining stages MUST remain visible alongside the partial transcript.

#### Scenario: Transcript appears before processing finishes

- **WHEN** transcript segments exist for a recording that is still `processing`
- **THEN** the detail view shows those segments
- **AND** the progress indication for the remaining stages is still shown

#### Scenario: Transcript updates when speakers are assigned

- **WHEN** diarization later assigns final speakers to an already-shown transcript
- **THEN** the displayed transcript updates to reflect the assigned speakers without a manual reload
