## MODIFIED Requirements

### Requirement: Capture microphone and system audio

The recorder SHALL capture the selected microphone input and, where available, the system audio output. The system audio output MAY be captured either natively (system output mix, no loopback device) or from a selected loopback input device, depending on the chosen system source. Each captured source MUST be written as its own track, and a mixed track MUST also be produced for playback.

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
