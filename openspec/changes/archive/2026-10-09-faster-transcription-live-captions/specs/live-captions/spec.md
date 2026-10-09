## ADDED Requirements

### Requirement: Live captions are optional and off by default

The system SHALL offer a live-captions setting that is off by default. Captions SHALL be available only where the on-device caption recognizer is supported (macOS 26 or later with the language asset installed); elsewhere the setting MUST be shown as unavailable with the reason.

#### Scenario: Default off

- **WHEN** the app is installed fresh
- **THEN** live captions are off and a recording runs without any speech recognition

#### Scenario: Unsupported system

- **WHEN** the system does not support the on-device caption recognizer
- **THEN** the live-captions setting is disabled and states why

### Requirement: Captions cover both tracks with low latency

When live captions are on, the system SHALL caption the microphone track as the user ("You") and the system track as the other side ("Others"). A provisional caption MUST appear within 2 seconds of the speech and a settled caption within 3 seconds under normal load. The caption text MUST be labeled by track.

#### Scenario: Both sides captioned

- **WHEN** the user and a remote participant speak during a recording with captions on
- **THEN** the user's speech appears as "You" and the remote speech as "Others" on the recording screen

#### Scenario: Provisional then settled

- **WHEN** a phrase is being spoken
- **THEN** a provisional caption appears and updates while it is spoken
- **AND** it is replaced by settled text shortly after the phrase ends

### Requirement: Captions stay light and never block recording

Caption recognition SHALL run on-device in a helper process separate from the recorder. Audio MUST be handed to it without blocking the capture path; if the helper falls behind or fails, the system MUST drop caption audio (not recorded audio), stop captioning, and keep recording. Caption work MUST stay within a small CPU budget (target: under 10% of one core on the reference Mac).

#### Scenario: Helper crash

- **WHEN** the caption helper exits during a recording
- **THEN** recording continues and the files on disk are complete
- **AND** the recording screen shows that captions stopped

#### Scenario: Helper falls behind

- **WHEN** the caption helper cannot keep up
- **THEN** caption audio is dropped and captions may skip, but no recorded audio is lost

### Requirement: Settled captions become the draft transcript

Settled captions SHALL be stored as draft transcript segments of the recording (with their track and time range), so the draft is available as soon as the recording stops.

#### Scenario: Draft from captions

- **WHEN** a recording with captions on is stopped
- **THEN** the recording already has draft segments covering the captioned speech
