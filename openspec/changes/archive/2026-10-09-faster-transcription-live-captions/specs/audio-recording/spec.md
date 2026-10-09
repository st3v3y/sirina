## MODIFIED Requirements

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

### Requirement: Live recording feedback without transcript

While recording, the UI SHALL display elapsed time and an input-level indicator. It SHALL NOT display a live transcript unless live captions are enabled, in which case it shows the captions (see `live-captions`).

#### Scenario: Recording screen shows timer and level only

- **WHEN** a recording is active, live captions are off, and the user views the recording screen
- **THEN** an elapsed timer and a level meter are shown
- **AND** no transcript text is shown

#### Scenario: Recording screen shows captions when enabled

- **WHEN** a recording is active and live captions are on
- **THEN** the elapsed timer and level meter are shown together with the live captions
