# device-selection-modal Specification

## Purpose
TBD - created by archiving change speaker-rename-and-ux-improvements. Update Purpose after archive.
## Requirements
### Requirement: Device selection happens in a modal on start

The system SHALL present microphone and system-audio selection in a modal shown when the user initiates a recording, rather than as a permanently visible form. Starting the recording SHALL require at least one audio source to be selected.

#### Scenario: Modal appears on start

- **WHEN** the user clicks "Start recording"
- **THEN** a modal is shown offering microphone and system-audio selection

#### Scenario: One source is sufficient

- **WHEN** the user selects only a microphone or only a system-audio source and confirms
- **THEN** the recording starts using the selected source

#### Scenario: No source blocks start

- **WHEN** the user confirms with neither source selected
- **THEN** the recording does not start
- **AND** the user is prompted to choose a source

### Requirement: Last-used devices are remembered

The system SHALL persist the most recently selected microphone and system-audio devices to local storage and pre-select them the next time the modal is shown.

#### Scenario: Pre-fill from last use

- **WHEN** the user has previously started a recording with chosen devices
- **THEN** the next time the modal opens, those devices are pre-selected

#### Scenario: Persist on start

- **WHEN** the user starts a recording with chosen devices
- **THEN** those device selections are saved to local storage

