## MODIFIED Requirements

### Requirement: Native system-audio capture without a loopback device

On macOS, Windows and Linux, the system SHALL be able to capture the system audio output mix natively, without the user installing or selecting a loopback input device, when a native capture helper is available. The output mix is the audio the user hears, including remote call participants. The sources are:
- **macOS**: ScreenCaptureKit.
- **Windows**: WASAPI loopback of the default render device.
- **Linux**: the monitor of the default PulseAudio/PipeWire sink.

The capture MUST exclude the application's own audio output where the platform supports it:
- always on macOS
- on Windows when process loopback is available

Where exclusion is not possible, the helper MUST report this so the recording records it as a known limitation. This applies to Windows endpoint-loopback fallback and to Linux. The capture MUST produce a `system` track equivalent to the device-loopback path: 48 kHz, mono, 16-bit.

#### Scenario: Native capture produces the system track

- **WHEN** a recording starts with native system-audio capture selected and available
- **THEN** the system output mix is captured to the `system` track without any loopback device
- **AND** the application's own playback is excluded from that track where the platform supports exclusion

#### Scenario: No loopback device required

- **WHEN** native capture is in use on any supported platform
- **THEN** the user is not asked to select or install a system-audio loopback device

#### Scenario: Windows process loopback excludes the app

- **WHEN** native capture runs on a Windows build that supports process loopback
- **THEN** audio rendered by Sirina's own process tree is not present in the `system` track

#### Scenario: Exclusion unavailable is reported

- **WHEN** native capture runs where the app's own audio cannot be excluded (Linux, or Windows endpoint-loopback fallback)
- **THEN** capture proceeds
- **AND** the helper reports that self-exclusion is off, and the backend logs it

#### Scenario: Nothing playing still yields a continuous track

- **WHEN** native capture runs and no application plays audio for a minute (e.g. Windows loopback delivering no packets)
- **THEN** the helper keeps emitting silence at the real-time rate
- **AND** the track is neither treated as stalled nor restarted, and stays aligned with the microphone track

#### Scenario: Helper exits when the backend dies

- **WHEN** the backend process is killed during a recording
- **THEN** the capture helper exits on its own once its output pipe closes

#### Scenario: Linux records the default sink monitor

- **WHEN** native capture runs on Linux with PulseAudio or PipeWire (pipewire-pulse)
- **THEN** the monitor of the default output sink is captured to the `system` track

### Requirement: Permission failure is surfaced

When native capture cannot proceed, the system SHALL fail the recording start with a clear, actionable message. Causes include:
- the macOS Screen Recording permission is denied
- no audio server or output device is reachable
- the helper fails to start

The system MUST NOT record a silent or empty system track in place of the far end.

#### Scenario: Permission denied is reported

- **WHEN** native capture is requested on macOS but Screen Recording permission is not granted
- **THEN** the start fails with a message directing the user to grant the permission
- **AND** no recording proceeds as if the far-end were captured

#### Scenario: No audio server on Linux

- **WHEN** native capture is requested on Linux and no PulseAudio-compatible server is reachable
- **THEN** the probe reports native capture as unavailable with that reason
- **AND** a start requesting native capture is rejected with the reason

#### Scenario: No output device on Windows

- **WHEN** native capture is requested on Windows and no audio render device is active
- **THEN** the start fails with a message saying no output device was found
