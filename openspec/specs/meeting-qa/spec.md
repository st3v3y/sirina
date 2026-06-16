# meeting-qa Specification

## Purpose
TBD - created by archiving change structured-summaries. Update Purpose after archive.
## Requirements
### Requirement: Grounded question answering over a recording

The system SHALL answer user questions about a recording using its transcript, and SHALL persist the question and answer.

#### Scenario: Answer uses the transcript

- **WHEN** a user asks a question about a recording with a transcript
- **THEN** the answer is generated from the transcript
- **AND** both the question and the answer are stored

#### Scenario: Unsupported answer is acknowledged

- **WHEN** a question cannot be answered from the transcript
- **THEN** the answer indicates the transcript does not cover it

### Requirement: Q&A history is retained per recording

Prior questions and answers for a recording SHALL be retained and available as context for subsequent questions.

#### Scenario: Follow-up uses prior turns

- **WHEN** a user asks a follow-up question
- **THEN** previous Q&A turns for that recording are available as context

