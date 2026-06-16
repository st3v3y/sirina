## ADDED Requirements

### Requirement: Section-wise summary generation

Generating a summary SHALL run each template section as its own LLM prompt over the recording transcript and store the result as structured sections (title + content).

#### Scenario: Each section produced independently

- **WHEN** a summary is generated from a template with three sections
- **THEN** three independent LLM calls produce three section contents
- **AND** the summary is stored as ordered (title, content) sections

#### Scenario: Prompts receive the transcript

- **WHEN** a section prompt references the transcript placeholder
- **THEN** the recording's transcript is substituted before the LLM call

### Requirement: Default summary generated automatically on completion

When a recording finishes transcription (becomes `ready`), the system SHALL automatically generate a summary using the default template.

#### Scenario: Auto-summary after transcription

- **WHEN** a recording transitions to `ready` with a transcript
- **THEN** a summary is generated using the default template without user action

#### Scenario: No transcript, no auto-summary

- **WHEN** a recording becomes `ready` but has no transcript (e.g. silence)
- **THEN** no summary is generated

### Requirement: Regenerate with a different template, keeping history

The system SHALL allow regenerating a summary with a chosen template, retaining previously generated summaries.

#### Scenario: Regenerate keeps prior summaries

- **WHEN** the user regenerates a summary with a different template
- **THEN** a new summary is stored
- **AND** the previously generated summary is still retained
