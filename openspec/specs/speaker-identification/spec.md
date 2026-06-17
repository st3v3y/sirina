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

When diarization is not in effect, a recording with both a microphone track and a system-audio track SHALL attribute microphone-track segments to a "You" speaker and system-track segments to an "Others" speaker, and a single-track recording SHALL attribute all segments to a single "Speaker 1". No user-supplied label and no additional placeholder speaker (such as "Room") SHALL be produced. When diarization is in effect, speakers are produced per the `speaker-diarization` capability instead.

#### Scenario: Two tracks split into You and Others

- **WHEN** diarization is not in effect and a recording captured both mic and system audio is transcribed
- **THEN** mic-track segments are attributed to a "You" speaker
- **AND** system-track segments are attributed to an "Others" speaker
- **AND** the combined transcript is ordered by time

#### Scenario: Single track yields one speaker

- **WHEN** diarization is not in effect and a recording captured only the microphone is transcribed
- **THEN** all segments are attributed to a single "Speaker 1"

#### Scenario: No phantom third speaker

- **WHEN** a two-person recording is transcribed
- **THEN** no extra placeholder speaker (e.g. "Room") appears in addition to the real speakers

#### Scenario: Diarization supersedes the baseline split

- **WHEN** diarization is in effect for a recording
- **THEN** speakers are produced by diarization clusters rather than the fixed You/Others split

### Requirement: Rename a speaker within a recording links to a Person

Renaming a speaker SHALL set that speaker's linked person — linking to an existing `Person` when the name matches one (case-insensitively), or creating a new `Person` only when the name is new and is not a default label. The rename MUST affect only the current recording's speaker and MUST NOT change speakers in other recordings.

#### Scenario: Renaming links to a Person

- **WHEN** the user renames a speaker to "Stefan"
- **THEN** that recording's speaker is linked to a Person named "Stefan" (created if absent, reused if an existing name matches)

#### Scenario: Rename is scoped to the recording

- **WHEN** the user renames a speaker in one recording
- **THEN** speakers with the same label in other recordings are unchanged

#### Scenario: Default speakers do not create People

- **WHEN** a recording finishes transcription with default speaker labels (e.g. "Speaker 1", "You", "Others")
- **THEN** no `Person` rows are created for those default labels
- **AND** the People directory is not populated until the user explicitly renames a speaker to a new, non-default name

### Requirement: Rename autocomplete from existing People

When renaming a speaker, the UI SHALL present existing `Person` names as selectable suggestions, and selecting an existing Person SHALL link the speaker to that Person without creating a duplicate.

#### Scenario: Suggestions come from prior People

- **WHEN** the user begins typing a new speaker name
- **THEN** matching existing Person names are suggested

#### Scenario: Selecting an existing Person links without duplicating

- **WHEN** the user picks an existing Person from the suggestions
- **THEN** the speaker is linked to that existing Person
- **AND** no new Person is created

### Requirement: Speakers have a stable display color

Each speaker SHALL have a stable color used to visually distinguish them in the transcript.

#### Scenario: Color persists across views

- **WHEN** a speaker is shown in the transcript
- **THEN** the same speaker is shown with the same color on subsequent views

### Requirement: Speakers are renamed inline from the transcript

The transcript view SHALL allow renaming a speaker by interacting directly with the speaker's chip/label in the transcript, without leaving the transcript view, and the rename SHALL apply to every line attributed to that speaker.

#### Scenario: Click a speaker chip to rename

- **WHEN** the user activates a speaker's chip in the transcript
- **THEN** an inline rename control is shown for that speaker

#### Scenario: Rename updates all of that speaker's lines

- **WHEN** the user confirms a changed name for a speaker
- **THEN** every transcript line attributed to that speaker shows the new name

### Requirement: Renaming a default label does not create a Person

A speaker SHALL NOT cause a `Person` to be created when the submitted name is empty, unchanged from the speaker's current display name, or equal to the speaker's own default label (e.g. "Speaker 1", "You", "Others"). This guard MUST hold in both the editing UI and the rename API.

#### Scenario: Dismissing the rename control without a change

- **WHEN** the user opens a speaker's rename control and confirms or blurs without changing the value
- **THEN** no rename is performed
- **AND** no `Person` is created

#### Scenario: Submitting a default label is rejected

- **WHEN** a rename request is made whose name equals the speaker's default label
- **THEN** the request is a no-op
- **AND** no `Person` named after a default label is created

#### Scenario: People directory stays empty until a real rename

- **WHEN** several recordings are transcribed and no speaker is deliberately renamed
- **THEN** the People directory contains no entries

