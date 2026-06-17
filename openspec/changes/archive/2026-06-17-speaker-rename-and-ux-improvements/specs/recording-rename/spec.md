## ADDED Requirements

### Requirement: Recordings can be renamed inline

The system SHALL allow renaming a recording's title from both the recording detail view and the recordings list, persisting the new title immediately.

#### Scenario: Rename from the detail view

- **WHEN** the user edits the title in the recording detail header and confirms
- **THEN** the recording's title is updated and persisted
- **AND** the new title is shown without a manual page reload

#### Scenario: Rename from the recordings list

- **WHEN** the user edits a recording's title in the dashboard list and confirms
- **THEN** the recording's title is updated and persisted
- **AND** the list reflects the new title

#### Scenario: Empty title falls back to default label

- **WHEN** the user clears the title and confirms
- **THEN** the stored title is empty
- **AND** the UI shows the default "Recording #<id>" label
