## ADDED Requirements

### Requirement: Native system-audio capture without a virtual device

The app SHALL be able to capture system audio using the operating system's native capture (ScreenCaptureKit on macOS) so that recording a call works without installing a virtual audio device (BlackHole) or configuring a Multi-Output Device.

#### Scenario: System audio captured natively

- **WHEN** native capture is used and the user records while audio plays through any output device
- **THEN** that system audio is captured into the recording's system track without a virtual audio device

#### Scenario: Microphone captured alongside

- **WHEN** native capture is used
- **THEN** the microphone is captured as its own track in parallel with system audio

### Requirement: Native frames feed the existing recorder pipeline

Audio captured natively SHALL feed the same recorder/processing pipeline as device capture, producing the same per-track files and downstream transcription.

#### Scenario: Same outputs regardless of capture source

- **WHEN** a recording is made via native capture
- **THEN** it produces the same mic/system/mixed tracks and is transcribed identically to a device-captured recording
