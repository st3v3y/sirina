# audio-recording Specification

## Purpose
TBD - created by archiving change record-to-file. Update Purpose after archive.
## Requirements
### Requirement: Recording performs no inference

While a recording is active, the system SHALL NOT run speech-to-text or LLM inference, and captured audio MUST be written to disk. The only exceptions are the opt-in live captions (see `live-captions`) and transcription during recording (see `live-transcription`); both MUST run on-device in a separate helper process and MUST NOT delay or drop audio written to disk. LLM inference MUST NOT run during a recording.

#### Scenario: No models run during capture

- **WHEN** a recording is active with live captions and transcription during recording both off
- **THEN** no transcription or LLM request is issued
- **AND** CPU usage attributable to the app is dominated by audio I/O, not inference

#### Scenario: Opt-in speech work does not affect capture

- **WHEN** a recording is active with live captions or transcription during recording on
- **THEN** only the speech helper runs speech recognition
- **AND** the recorded audio files are identical in length and content to a recording with both off

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

### Requirement: Start returns immediately

Starting a recording SHALL return promptly without waiting for any model to load or any processing to occur.

#### Scenario: Start does not block on model load

- **WHEN** a client starts a recording
- **THEN** the call returns a recording identifier without loading the transcription model

### Requirement: Stop finalizes and hands off to processing

Stopping a recording SHALL finalize the audio files, compute the recording duration, set the recording status to `processing`, and return. The actual transcription/processing is performed by a separate job (out of scope for this capability).

#### Scenario: Stop finalizes files and marks processing

- **WHEN** a client stops an active recording
- **THEN** the audio files are closed and readable
- **AND** the recording's duration is stored
- **AND** the recording status becomes `processing`

### Requirement: Live recording feedback without transcript

While recording, the UI SHALL display elapsed time and an input-level indicator. It SHALL NOT display a live transcript unless live captions are enabled, in which case it shows the captions (see `live-captions`).

#### Scenario: Recording screen shows timer and level only

- **WHEN** a recording is active, live captions are off, and the user views the recording screen
- **THEN** an elapsed timer and a level meter are shown
- **AND** no transcript text is shown

#### Scenario: Recording screen shows captions when enabled

- **WHEN** a recording is active and live captions are on
- **THEN** the elapsed timer and level meter are shown together with the live captions

