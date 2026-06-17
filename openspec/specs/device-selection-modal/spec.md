# device-selection-modal Specification

## Purpose
TBD - created by archiving change speaker-rename-and-ux-improvements. Update Purpose after archive.
## Requirements
### Requirement: Device selection happens in a modal on start

The system SHALL present audio-source selection in a modal shown when the user initiates a recording, rather than as a permanently visible form. When native system-audio capture is available, the modal SHALL ask only for the microphone and indicate that system audio (other participants) is captured automatically. When native capture is unavailable, the modal SHALL offer both a microphone and a system-audio (loopback) device selector. Starting the recording SHALL require at least one audio source.

#### Scenario: Modal appears on start

- **WHEN** the user clicks "Start recording"
- **THEN** a modal is shown for audio-source selection

#### Scenario: Native available hides the system-audio device picker

- **WHEN** native system-audio capture is available
- **THEN** the modal asks only for the microphone
- **AND** it indicates that system audio is captured automatically

#### Scenario: Native unavailable offers the device picker

- **WHEN** native system-audio capture is not available
- **THEN** the modal offers both microphone and system-audio device selection

#### Scenario: One source is sufficient

- **WHEN** the user selects only a microphone or only a system-audio source and confirms
- **THEN** the recording starts using the selected source

#### Scenario: No source blocks start

- **WHEN** the user confirms with no audio source available
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

