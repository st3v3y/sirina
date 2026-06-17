## ADDED Requirements

### Requirement: Cross-recording chat sessions

The system SHALL provide a chat surface where the user can create sessions and ask questions answered using the transcripts of multiple recordings. Sessions and their messages MUST be persisted.

#### Scenario: Create a session and ask

- **WHEN** the user starts a new cross-recording chat session and asks a question
- **THEN** the system answers using available recording transcripts as context
- **AND** the question and answer are stored in that session

#### Scenario: Multiple independent sessions

- **WHEN** the user creates more than one chat session
- **THEN** each session retains its own message history independently

#### Scenario: Follow-up uses prior turns in the session

- **WHEN** the user asks a follow-up within a session
- **THEN** prior turns in that session are available as context

### Requirement: Cross-recording context is bounded

When answering a cross-recording question, the system SHALL build context from recording transcripts within a bounded size, preferring the most recent recordings, and SHALL indicate when older content was omitted.

#### Scenario: Context fits within the budget

- **WHEN** the combined transcripts fit within the context budget
- **THEN** all are included

#### Scenario: Context exceeds the budget

- **WHEN** the combined transcripts exceed the context budget
- **THEN** the most recent recordings are included up to the budget
- **AND** the answer notes that older recordings were omitted
