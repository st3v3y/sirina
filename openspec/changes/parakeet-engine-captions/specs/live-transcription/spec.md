## MODIFIED Requirements

### Requirement: Only the low-resource engine runs during recording

Transcription during recording SHALL run only with an engine qualified as light enough for a live call: WhisperKit, or Parakeet if the spike in this change qualifies it. When no qualified engine is active or its model is unavailable, the option MUST be shown as unavailable with the reason, and the recording is transcribed after stop as usual. The faster-whisper engine MUST NOT run during a recording, on CPU or GPU.

#### Scenario: WhisperKit unavailable

- **WHEN** the WhisperKit model is not installed and Parakeet is not the active engine
- **THEN** the option is disabled in the start dialog and on the recording screen with the reason
- **AND** transcription starts after stop

#### Scenario: Parakeet during a call

- **WHEN** Parakeet is the active engine, it is qualified for live use, and transcription during recording is on
- **THEN** final windows are committed during the recording as with WhisperKit

#### Scenario: faster-whisper active

- **WHEN** faster-whisper is the active engine
- **THEN** transcription during recording is unavailable with a reason that the selected engine is too heavy to run during a call

## ADDED Requirements

### Requirement: Low-power state is detected on Windows and Linux

The low-power state that pauses transcription during recording SHALL be detected on every platform:
- **macOS**: Low Power Mode.
- **Windows**: Battery Saver.
- **Linux**: the power-saver profile when power-profiles-daemon is present.

Where the state cannot be read, it MUST count as off.

#### Scenario: Battery Saver on Windows

- **WHEN** Battery Saver turns on during a recording with Parakeet live transcription on
- **THEN** no new window starts while it stays on, and the recording screen shows that live transcription is paused

#### Scenario: No power-profiles-daemon on Linux

- **WHEN** the Linux system has no power-profiles-daemon
- **THEN** the low-power state counts as off and live transcription runs normally
