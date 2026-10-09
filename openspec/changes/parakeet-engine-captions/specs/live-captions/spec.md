## MODIFIED Requirements

### Requirement: Live captions are optional and off by default

The system SHALL offer a live-captions setting that is off by default. Captions SHALL be available only where a caption recognizer that meets the latency targets is shipped for the platform:
- **macOS 26 or later**: Apple's on-device recognizer, with its language asset installed.
- **Other platforms, and macOS without it**: the Parakeet caption worker, when this platform's build ships it and its models are installed.

Elsewhere, the setting MUST be shown as unavailable with a reason that names the cause. Possible causes:
- the OS version is too old
- no near-real-time recognizer is available on this platform yet
- the caption model is not installed
- the machine was too slow to keep captions up

#### Scenario: Default off

- **WHEN** the app is installed fresh
- **THEN** live captions are off and a recording runs without any speech recognition

#### Scenario: Unsupported system

- **WHEN** the system has no caption recognizer that meets the targets
- **THEN** the live-captions setting is disabled and states why

#### Scenario: Windows or Linux without a shipped recognizer

- **WHEN** the app runs on Windows or Linux and this build does not ship Parakeet captions
- **THEN** the live-captions option is disabled with an explanation that near-real-time captions are not available on this platform yet

#### Scenario: Caption model missing

- **WHEN** Parakeet captions ship for the platform but the Parakeet model is not installed
- **THEN** the option is disabled with a reason and a way to install the model

### Requirement: Captions stay light and never block recording

Caption recognition SHALL run on-device in a process separate from the recorder. Audio MUST be handed to it without blocking the capture path. If the recognizer falls behind or fails, the system MUST drop caption audio (not recorded audio), stop captioning, and keep recording. Caption work MUST stay within a per-recognizer CPU budget:
- **Apple recognizer**: under 10% of one core on the reference Mac.
- **Parakeet caption worker**: an average of at most one core for both tracks together on the reference x64 machine. The spike in this change measures it.

When captions are stopped because the recognizer could not keep up, the recording screen MUST say so.

#### Scenario: Helper crash

- **WHEN** the caption process exits during a recording
- **THEN** recording continues and the files on disk are complete
- **AND** the recording screen shows that captions stopped

#### Scenario: Helper falls behind

- **WHEN** the caption process cannot keep up
- **THEN** caption audio is dropped and captions may skip, but no recorded audio is lost

#### Scenario: Machine too slow for Parakeet captions

- **WHEN** the Parakeet caption worker keeps falling behind during a recording
- **THEN** captions stop for this recording with a message that this computer is too slow for live captions
- **AND** recording continues unaffected
