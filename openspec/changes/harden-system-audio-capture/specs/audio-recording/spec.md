## MODIFIED Requirements

### Requirement: Capture microphone and system audio

The recorder SHALL capture the selected microphone input and, where available, the system audio output. The system audio output MAY be captured either natively (system output mix, no loopback device) or from a selected loopback input device, depending on the chosen system source. Each captured source MUST be written as its own track, and a mixed track MUST also be produced for playback. If one source stops delivering audio mid-recording, the recorder MUST keep capturing the remaining source(s) for the full duration, and MUST NOT present a partial track as if it were complete.

#### Scenario: Two sources captured to separate tracks

- **WHEN** both a microphone and a system-audio source are available and a recording runs
- **THEN** a `mic` track and a `system` track are written to disk as separate files
- **AND** a `mixed` track combining both is also written

#### Scenario: System track from native capture

- **WHEN** the system source is native capture
- **THEN** the `system` track is written from the captured system output mix without a loopback device

#### Scenario: System track from a loopback device

- **WHEN** the system source is a loopback input device
- **THEN** the `system` track is written from that device's input

#### Scenario: Single source still records

- **WHEN** only a microphone is available
- **THEN** the recording succeeds using the microphone track as both the primary and mixed track

#### Scenario: One source stops mid-recording

- **WHEN** one source stops delivering audio partway through a recording
- **THEN** the remaining source continues to be captured to its track for the full recording
- **AND** the resulting mixed track is not presented as if the stopped source were captured for its entire span

## ADDED Requirements

### Requirement: Prevent idle sleep during recording

While a recording is active, the system SHALL prevent idle system and display sleep so that capture (both microphone and system audio) is not silently interrupted by the machine sleeping. The prevention MUST be scoped to the recording: it is released when the recording stops or the process exits.

#### Scenario: Sleep prevented while recording

- **WHEN** a recording is active and the user is not interacting with the machine
- **THEN** the system does not enter idle display or system sleep for the duration of the recording

#### Scenario: Sleep prevention released on stop

- **WHEN** the recording stops
- **THEN** normal idle-sleep behavior is restored
