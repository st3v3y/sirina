## ADDED Requirements

### Requirement: Tags can be created, renamed, recolored, and deleted

The system SHALL let users manage a set of tags, each with a name and an optional color.

#### Scenario: Create a tag

- **WHEN** a user creates a tag with a name
- **THEN** the tag is persisted and available to assign to recordings

#### Scenario: Rename or recolor a tag

- **WHEN** a user changes a tag's name or color
- **THEN** the change is reflected everywhere the tag is shown

#### Scenario: Delete a tag

- **WHEN** a user deletes a tag
- **THEN** the tag is removed from all recordings it was assigned to
- **AND** the recordings themselves are unaffected

### Requirement: Tags can be assigned to and removed from recordings

A recording SHALL be able to carry zero or more tags, and the user SHALL be able to add or remove a tag on a recording.

#### Scenario: Assign a tag

- **WHEN** a user adds a tag to a recording
- **THEN** the recording lists that tag

#### Scenario: Remove a tag

- **WHEN** a user removes a tag from a recording
- **THEN** the recording no longer lists that tag
- **AND** the tag still exists for use elsewhere

### Requirement: Recordings can be filtered by tag

The recordings list SHALL support filtering to only recordings carrying a selected tag.

#### Scenario: Filter the list by a tag

- **WHEN** a user filters the recordings list by a tag
- **THEN** only recordings carrying that tag are shown

#### Scenario: Clearing the filter

- **WHEN** the tag filter is cleared
- **THEN** all recordings are shown again
