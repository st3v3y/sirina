## ADDED Requirements

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
