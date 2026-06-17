# transcript-view Specification

## Purpose
TBD - created by archiving change offline-transcription. Update Purpose after archive.
## Requirements
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

### Requirement: Transcript and Chat are separate tabs

The recording detail view SHALL present the transcript and the AI chat (Q&A) on separate tabs, so that questions and answers do not interleave with transcript content.

#### Scenario: Switching tabs

- **WHEN** the user opens a recording with a transcript
- **THEN** a Transcript tab shows only transcript segments
- **AND** a Chat tab shows the Q&A conversation and the prompt input

#### Scenario: Q&A does not appear in the transcript

- **WHEN** the user asks a question from the Chat tab
- **THEN** the question and answer appear in the Chat tab
- **AND** they do not appear within the Transcript tab's content

### Requirement: Transcript renders progressively while processing

The recording detail view SHALL render transcript segments as soon as they are available, while the recording is still `processing`, rather than only after it becomes `ready`. The progress indication for the remaining stages MUST remain visible alongside the partial transcript.

#### Scenario: Transcript appears before processing finishes

- **WHEN** transcript segments exist for a recording that is still `processing`
- **THEN** the detail view shows those segments
- **AND** the progress indication for the remaining stages is still shown

#### Scenario: Transcript updates when speakers are assigned

- **WHEN** diarization later assigns final speakers to an already-shown transcript
- **THEN** the displayed transcript updates to reflect the assigned speakers without a manual reload

