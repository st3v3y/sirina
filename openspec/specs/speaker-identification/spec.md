# speaker-identification Specification

## Purpose
TBD - created by archiving change speakers-and-people. Update Purpose after archive.
## Requirements
### Requirement: Segments are attributed to per-recording speakers

Each recording SHALL have a set of speakers, and every transcript segment MUST be attributed to one of that recording's speakers. Speakers are scoped to a single recording.

#### Scenario: Segments reference a speaker

- **WHEN** a recording is transcribed
- **THEN** each `Segment` is linked to a `Speaker` belonging to that recording

#### Scenario: Speakers are per-recording

- **WHEN** two different recordings are transcribed
- **THEN** each has its own independent set of `Speaker` rows

### Requirement: Baseline two-track speaker split

When diarization is not in effect, a recording with both a microphone track and a system-audio track SHALL attribute microphone-track segments to a "You" speaker and system-track segments to an "Others" speaker, and a single-track recording SHALL attribute all segments to a single speaker. When diarization is in effect, speakers are produced per the `speaker-diarization` capability instead.

#### Scenario: Two tracks split into You and Others

- **WHEN** diarization is not in effect and a recording captured both mic and system audio is transcribed
- **THEN** mic-track segments are attributed to a "You" speaker
- **AND** system-track segments are attributed to an "Others" speaker
- **AND** the combined transcript is ordered by time

#### Scenario: Single track yields one speaker

- **WHEN** diarization is not in effect and a recording captured only the microphone is transcribed
- **THEN** all segments are attributed to a single speaker

#### Scenario: Diarization supersedes the baseline split

- **WHEN** diarization is in effect for a recording
- **THEN** speakers are produced by diarization clusters rather than the fixed You/Others split

### Requirement: Rename a speaker within a recording links to a Person

Renaming a speaker SHALL set that speaker's linked person (creating a `Person` if the name is new). The rename MUST affect only the current recording's speaker and MUST NOT change speakers in other recordings.

#### Scenario: Renaming links to a Person

- **WHEN** the user renames a speaker to "Stefan"
- **THEN** that recording's speaker is linked to a Person named "Stefan" (created if absent)

#### Scenario: Rename is scoped to the recording

- **WHEN** the user renames a speaker in one recording
- **THEN** speakers with the same label in other recordings are unchanged

### Requirement: Rename autocomplete from existing People

When renaming a speaker, the UI SHALL offer autocomplete suggestions drawn from existing `Person` names.

#### Scenario: Suggestions come from prior People

- **WHEN** the user begins typing a new speaker name
- **THEN** matching existing Person names are suggested

### Requirement: Speakers have a stable display color

Each speaker SHALL have a stable color used to visually distinguish them in the transcript.

#### Scenario: Color persists across views

- **WHEN** a speaker is shown in the transcript
- **THEN** the same speaker is shown with the same color on subsequent views

