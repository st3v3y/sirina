# speaker-diarization Specification

## Purpose
TBD - created by archiving change enhanced-diarization. Update Purpose after archive.
## Requirements
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

Diarization SHALL run only when enabled and the on-device diarizer (SpeakerKit in the speech helper) and its model are available; no access token is required. When it is disabled, unavailable, or fails for any reason, the system MUST fall back to the baseline mic/system split and MUST NOT fail the recording.

#### Scenario: Disabled by configuration

- **WHEN** diarization is disabled
- **THEN** the baseline mic/system split is used and no diarization model is loaded

#### Scenario: Diarizer unavailable falls back

- **WHEN** diarization is enabled but the speech helper or its diarization model is unavailable
- **THEN** the baseline split is used, the recording still completes, and the reason is noted on the recording

#### Scenario: Diarization error falls back

- **WHEN** diarization is enabled but the diarization step raises an error
- **THEN** the baseline split is used, the recording still becomes `ready`, and the transcript is intact

### Requirement: Negligible diarization clusters are discarded

When diarization produces a cluster whose total speech duration is below a minimum threshold (both an absolute floor and a share of the track), the system SHALL discard that cluster rather than emit it as a separate speaker, reassigning or dropping its words so brief room noise or cross-talk does not appear as a phantom "Speaker N". At least one speaker MUST always remain.

#### Scenario: Brief noise cluster is dropped

- **WHEN** diarization splits a two-person track into clusters and one cluster's total speech is below the minimum threshold
- **THEN** that cluster is not emitted as a separate speaker
- **AND** the remaining speakers reflect the real participants

#### Scenario: Genuine speakers are preserved

- **WHEN** every diarization cluster exceeds the minimum threshold
- **THEN** all clusters are emitted as speakers unchanged

#### Scenario: At least one speaker remains

- **WHEN** thresholding would remove all clusters
- **THEN** at least one speaker is still produced for the track

### Requirement: Speaker splitting runs on-device with SpeakerKit

Speaker splitting SHALL use SpeakerKit through the speech helper instead of pyannote. The app MUST NOT bundle pyannote or torch for diarization. On the reference Mac a 2-hour track MUST split in about a minute.

#### Scenario: Two-hour meeting

- **WHEN** a 2h14 two-track recording finishes transcription with diarization enabled
- **THEN** the system track is split into speakers within about a minute

### Requirement: When speakers are split is a setting

A setting SHALL choose when speakers are split: "after the recording" (default) or "also during the recording". With "also during the recording", the system SHALL re-split the system track of an active recording about every 10 minutes and label the final segments so far; the run after stop is always performed and is authoritative.

#### Scenario: Default after stop

- **WHEN** the setting is left at its default
- **THEN** no speaker splitting runs during the recording and it runs once after stop

#### Scenario: During the recording

- **WHEN** the setting is "also during the recording" and a recording with transcription during recording runs for 25 minutes
- **THEN** speaker labels for the final segments so far have been updated at about 10 and 20 minutes
- **AND** a final split still runs after stop

### Requirement: Voice fingerprints are re-learned after the diarizer change

Voice fingerprints SHALL be tagged with the diarizer that produced them. Fingerprints from a different diarizer (the stored pyannote ones) MUST NOT be compared with new ones; they are cleared once on upgrade, and People keep their names and links. New fingerprints build up from renames as before.

#### Scenario: First recording after upgrade

- **WHEN** a recording is diarized for the first time after the upgrade
- **THEN** no speaker is auto-linked to a Person from an old pyannote fingerprint
- **AND** renaming a speaker to an existing Person enrolls a new fingerprint for that Person

