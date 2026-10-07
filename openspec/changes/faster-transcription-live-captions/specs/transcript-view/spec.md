## MODIFIED Requirements

### Requirement: Transcript renders progressively while processing

The recording detail view SHALL render transcript segments as soon as they are available, while the recording is still `processing`, rather than only after it becomes `ready`. Draft segments MUST be shown visually distinct from final segments (muted text and a "draft" marker), and the boundary between final and draft MUST move forward as final windows commit, without a manual reload. The progress indication for the remaining stages MUST remain visible alongside the partial transcript.

#### Scenario: Transcript appears before processing finishes

- **WHEN** transcript segments exist for a recording that is still `processing`
- **THEN** the detail view shows those segments
- **AND** the progress indication for the remaining stages is still shown

#### Scenario: Draft shown distinct from final

- **WHEN** a recording has final segments up to 12:00 and draft segments after it
- **THEN** lines before 12:00 render in the normal style
- **AND** lines after 12:00 render muted with a "draft" marker

#### Scenario: Boundary moves without reload

- **WHEN** a further final window commits while the user is viewing the recording
- **THEN** the affected lines switch from draft to final style without a manual reload

#### Scenario: Transcript updates when speakers are assigned

- **WHEN** diarization later assigns final speakers to an already-shown transcript
- **THEN** the displayed transcript updates to reflect the assigned speakers without a manual reload

#### Scenario: Speaker rename applies to draft and final lines

- **WHEN** the user renames "You" while the final pass is still running
- **THEN** both draft and final lines of that speaker show the new name, and later windows keep it
