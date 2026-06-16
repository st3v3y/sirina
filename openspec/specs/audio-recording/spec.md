# audio-recording Specification

## Purpose
TBD - created by archiving change record-to-file. Update Purpose after archive.
## Requirements
### Requirement: Recording performs no inference

While a recording is active, the system SHALL NOT run speech-to-text or LLM inference. Captured audio MUST only be written to disk.

#### Scenario: No models run during capture

- **WHEN** a recording is active
- **THEN** no whisper transcription or Ollama request is issued
- **AND** CPU usage attributable to the app is dominated by audio I/O, not inference

### Requirement: Capture microphone and system audio

The recorder SHALL capture the selected microphone input and, where available, the system audio output. Each available source MUST be written as its own track, and a mixed track MUST also be produced for playback.

#### Scenario: Two sources captured to separate tracks

- **WHEN** both a microphone and a system-audio source are available and a recording runs
- **THEN** a `mic` track and a `system` track are written to disk as separate files
- **AND** a `mixed` track combining both is also written

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

While recording, the UI SHALL display elapsed time and an input-level indicator, and SHALL NOT display a live transcript.

#### Scenario: Recording screen shows timer and level only

- **WHEN** a recording is active and the user views the recording screen
- **THEN** an elapsed timer and a level meter are shown
- **AND** no transcript text is shown

