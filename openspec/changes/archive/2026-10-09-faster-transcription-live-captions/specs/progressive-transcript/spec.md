## ADDED Requirements

### Requirement: A draft transcript exists right after stop

When a recording stops, the system SHALL make a draft transcript available before the final pass starts. If live captions produced draft segments, those are used; otherwise the system SHALL run a fast on-device draft pass over each non-silent track (target: under 2 minutes per hour of audio on the reference Mac). If no on-device draft recognizer is available, the system MUST skip the draft and continue with the final pass.

#### Scenario: Draft without captions

- **WHEN** a recording made with captions off is stopped on a supported Mac
- **THEN** draft segments for both tracks are stored before the first final window is written

#### Scenario: No draft recognizer

- **WHEN** the on-device draft recognizer is unavailable
- **THEN** no draft is produced and the final pass runs as usual

### Requirement: Draft segments are marked and replaced window by window

Each transcript segment SHALL record whether it is draft or final. As each final window completes, the system MUST atomically delete the draft segments of all tracks that start inside that window and insert the final segments for it. Draft and final segments MUST never overlap in time for the same recording after a window commits.

#### Scenario: Window replaces draft

- **WHEN** the final window covering 0:00–3:10 completes
- **THEN** draft segments starting before 3:10 are gone
- **AND** the recording's stored `final_until_s` is 190
- **AND** final segments for both tracks in 0:00–3:10 are stored in the same transaction

#### Scenario: Processing stopped midway

- **WHEN** the user stops processing after some windows
- **THEN** the finalized windows keep their final segments and the rest keep their draft segments, still marked as draft

### Requirement: Drafts never feed summaries or exports

The summary and exports SHALL use final segments only. Q&A MAY use draft segments for the not-yet-final part, and MUST mark them as draft text in what it sends to the model.

#### Scenario: Summary ignores drafts

- **WHEN** a summary is generated for a recording that still has draft segments
- **THEN** only final segments are used

#### Scenario: Ask right after a call

- **WHEN** the user asks a question while the final pass is still running
- **THEN** the answer can use the draft part, which the prompt labels as draft

### Requirement: Both tracks advance together

The final pass SHALL process windows in time order, and within each window SHALL transcribe every non-silent track before committing, so the user's and the other side's lines become final together. Window boundaries MUST fall in a silence common to all transcribed tracks; when no common silence exists near the target length, the nearest silence in any track MAY be used, with the window still committed for all tracks at that time.

#### Scenario: Interleaved finalization

- **WHEN** a two-track recording is processed
- **THEN** the "You" and "Others" lines of a time window become final in the same commit

### Requirement: The draft/final boundary is exposed

The system SHALL store the time up to which the transcript is final (`final_until_s`) on the recording and expose it in the recording's progress while processing.

#### Scenario: Boundary moves forward

- **WHEN** a window ending at 6:20 commits
- **THEN** the recording's progress reports `final_until_s` of 6:20 (380 s)
