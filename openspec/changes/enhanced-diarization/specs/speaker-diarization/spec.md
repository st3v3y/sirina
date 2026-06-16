## ADDED Requirements

### Requirement: Optional local diarization splits a track into multiple speakers

When diarization is enabled and available, the system SHALL run local speaker diarization on the non-microphone audio (the system track of a two-track recording, or the single track of a mic-only recording) and produce one speaker per detected cluster (`Speaker 1..N`). The microphone track of a two-track recording remains a single "You" speaker.

#### Scenario: System track split into multiple speakers

- **WHEN** diarization is enabled and a two-track recording's system audio contains multiple voices
- **THEN** the system track yields multiple speakers (`Speaker 1`, `Speaker 2`, …)
- **AND** the microphone track remains a single "You" speaker

#### Scenario: Single-track in-room recording split by diarization

- **WHEN** diarization is enabled and a mic-only recording contains multiple voices
- **THEN** the recording yields one speaker per detected cluster

### Requirement: Segments assigned to the maximally overlapping speaker

Each transcript segment SHALL be assigned to the diarization cluster with the greatest temporal overlap with that segment.

#### Scenario: Overlap-based assignment

- **WHEN** a transcript segment overlaps two diarization turns
- **THEN** the segment is attributed to the speaker whose turn overlaps it most

### Requirement: Diarization is gated and degrades gracefully

Diarization SHALL run only when explicitly enabled and the required access token is present. When it is disabled, the token is missing, or diarization fails for any reason, the system MUST fall back to the baseline mic/system split and MUST NOT fail the recording.

#### Scenario: Disabled by configuration

- **WHEN** diarization is disabled
- **THEN** the baseline mic/system split is used and no diarization model is loaded

#### Scenario: Missing token falls back

- **WHEN** diarization is enabled but no access token is configured
- **THEN** the baseline split is used and the recording still completes

#### Scenario: Diarization error falls back

- **WHEN** diarization is enabled but the diarization step raises an error
- **THEN** the baseline split is used, the recording still becomes `ready`, and the transcript is intact
