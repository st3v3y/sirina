## MODIFIED Requirements

### Requirement: Capture microphone and system audio

The recorder SHALL capture the selected microphone input and, where available, the system audio output. Each available source MUST be written as its own track, and a mixed track MUST also be produced for playback. System audio MAY be sourced either from an audio input device (e.g. a virtual device such as BlackHole) or from the operating system's native capture (per the `native-audio-capture` capability); the recorder behaves the same regardless of the source.

#### Scenario: Two sources captured to separate tracks

- **WHEN** both a microphone and a system-audio source are available and a recording runs
- **THEN** a `mic` track and a `system` track are written to disk as separate files
- **AND** a `mixed` track combining both is also written

#### Scenario: Single source still records

- **WHEN** only a microphone is available
- **THEN** the recording succeeds using the microphone track as both the primary and mixed track

#### Scenario: System audio via native capture needs no virtual device

- **WHEN** native system-audio capture is available and selected
- **THEN** the system track is produced without requiring a virtual audio device or a Multi-Output Device
