## ADDED Requirements

### Requirement: Native capture detects and reports stream stop

The native capture helper SHALL observe its own capture stream and detect when the system stops the stream (for example on display sleep, permission loss, or system pressure). On such a stop, the helper MUST report the reason and terminate (closing its output) rather than continuing to run while emitting no audio.

#### Scenario: Stream stops mid-capture

- **WHEN** the capture stream is stopped by the system while a recording is in progress
- **THEN** the helper reports the stop reason
- **AND** the helper exits and closes its output stream rather than producing silence indefinitely

#### Scenario: Consumer observes the stop promptly

- **WHEN** the helper exits after a stream stop
- **THEN** the consuming recorder observes end-of-output promptly instead of blocking indefinitely

### Requirement: Native capture is restartable to continue a track

When the native capture helper stops or stalls during an active recording, the system SHALL be able to restart the helper and continue writing the same system track, bounding any audio loss to a short gap. Restarts MUST be bounded so a permanently unavailable source does not cause an unbounded restart loop.

#### Scenario: Helper restarted after a stall

- **WHEN** the helper stops during an active recording and capture is still possible
- **THEN** the recorder restarts the helper and resumes writing the same system track
- **AND** only the brief gap during recovery is missing from the track

#### Scenario: Restarts stop when capture is permanently unavailable

- **WHEN** the helper repeatedly fails to resume capture (e.g. permission was revoked)
- **THEN** restart attempts stop after a bounded number of tries
- **AND** the system track is marked stopped and the loss is surfaced to the user
