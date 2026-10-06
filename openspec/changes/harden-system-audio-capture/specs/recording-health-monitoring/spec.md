## ADDED Requirements

### Requirement: Per-track liveness watchdog during capture

While a recording is active, the system SHALL monitor each captured track for ongoing data flow and SHALL detect when a track stops producing audio (data ceases to be written) within a bounded time. Detection MUST be based on data progress (frames written), not on audio level, so that a genuinely silent but live source is not treated as stalled.

#### Scenario: Stalled track is detected and logged

- **WHEN** a track stops producing data for longer than the stall threshold while the recording is active
- **THEN** the track is marked unhealthy
- **AND** a warning is logged identifying which track stalled

#### Scenario: Silent but live track is not flagged

- **WHEN** a track is delivering audio that happens to be silence (frames still advancing)
- **THEN** the track remains healthy and is not reported as stalled

#### Scenario: Mic track stall is detected

- **WHEN** the microphone source stops delivering data mid-recording (e.g. the input device disconnects)
- **THEN** the mic track is marked unhealthy and logged, and the recording continues with the remaining track(s)

### Requirement: Dropped input is reopened and the gap kept aligned

When a stalled input device track (mic or loopback device) can be reopened, the system SHALL resume capturing into the same track, retrying with backoff until the recording stops. The mic SHALL fall back to the system default input when its device is gone or keeps stalling; a loopback system track MUST NOT fall back to another input. Any outage (on any track, including a restarted native system-audio capture) SHALL be filled with silence so the track stays time-aligned with the others, and SHALL be noted on the recording.

#### Scenario: Mic device disconnects and another input is available

- **WHEN** the mic's device disappears mid-recording (e.g. Bluetooth earbuds disconnect) and a default input exists
- **THEN** capture resumes on the default input, the outage is filled with silence, and the recording notes when the mic dropped, for how long, and which device it continued on

#### Scenario: Mic device briefly glitches

- **WHEN** the mic stops delivering but its device is still present
- **THEN** capture is reopened on the same device and the gap is filled with silence

### Requirement: Track health surfaced to clients live

The system SHALL expose per-track health for the active recording so clients can show the user, during recording, that a source has stopped delivering audio.

#### Scenario: Health reported in active recording info

- **WHEN** a client queries the active recording info
- **THEN** the response indicates, per track, whether it is currently healthy or has stopped delivering audio

#### Scenario: Recording screen warns on a stopped track

- **WHEN** a track is unhealthy while the user views the recording screen
- **THEN** a clear warning is shown that the affected audio source has stopped

### Requirement: Incomplete track is recorded and surfaced after stop

When a recording stops with a source track materially shorter than the recording duration (such that the mix must pad it with silence), the system SHALL persist a warning on the recording describing the shortfall and SHALL NOT present the partial track as complete.

#### Scenario: Short system track leaves a warning

- **WHEN** a recording stops and the system track is materially shorter than the recording duration
- **THEN** a warning is stored on the recording describing how much of the source was captured
- **AND** the warning is visible to the user when viewing the recording

#### Scenario: Complete tracks leave no warning

- **WHEN** all source tracks span the full recording duration within tolerance
- **THEN** no incompleteness warning is recorded
