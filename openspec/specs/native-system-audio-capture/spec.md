# native-system-audio-capture Specification

## Purpose
TBD - created by archiving change native-system-audio-capture. Update Purpose after archive.
## Requirements
### Requirement: Native system-audio capture without a loopback device

On macOS, the system SHALL be able to capture the system audio output mix (the audio the user hears, including remote call participants) natively, without requiring a loopback input device, when a native capture helper is available. The capture MUST exclude the application's own audio output to avoid feedback, and MUST produce a `system` track equivalent to the device-loopback path.

#### Scenario: Native capture produces the system track

- **WHEN** a recording starts with native system-audio capture selected and available
- **THEN** the system output mix is captured to the `system` track without any loopback device
- **AND** the application's own playback is excluded from that track

#### Scenario: No loopback device required

- **WHEN** native capture is in use
- **THEN** the user is not asked to select or install a system-audio loopback device

### Requirement: Native capture availability is detectable

The system SHALL expose whether native system-audio capture is available in the current runtime (helper present and runnable), so clients can adapt the start flow.

#### Scenario: Availability reported to clients

- **WHEN** a client queries audio capabilities
- **THEN** the response indicates whether native system-audio capture is available

#### Scenario: Unavailable in the browser/dev runtime

- **WHEN** the native helper is absent (e.g. running via a plain browser, not the desktop app)
- **THEN** capabilities report native capture as unavailable

### Requirement: Source selection between native and device loopback

Starting a recording SHALL allow choosing the system-audio source: native capture, a loopback input device, or none. Requesting native capture when it is unavailable MUST be rejected with a clear error rather than silently dropping the far-end audio.

#### Scenario: Native chosen and available

- **WHEN** a recording requests native system audio and it is available
- **THEN** the recording captures system audio natively

#### Scenario: Native chosen but unavailable

- **WHEN** a recording requests native system audio and it is not available
- **THEN** the start is rejected with an error indicating native capture is unavailable

#### Scenario: Device loopback chosen

- **WHEN** a recording requests a loopback input device as the system source
- **THEN** the recording captures system audio from that device (the existing fallback path)

### Requirement: Permission failure is surfaced

When native capture cannot proceed because the required macOS Screen Recording permission is denied (or the helper fails to start), the system SHALL fail the recording start with a clear, actionable message and MUST NOT record a silent or empty system track in place of the far-end.

#### Scenario: Permission denied is reported

- **WHEN** native capture is requested but Screen Recording permission is not granted
- **THEN** the start fails with a message directing the user to grant the permission
- **AND** no recording proceeds as if the far-end were captured

