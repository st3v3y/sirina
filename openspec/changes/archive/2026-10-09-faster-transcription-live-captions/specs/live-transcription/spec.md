## ADDED Requirements

### Requirement: Transcribe-during-recording is chosen per recording

The system SHALL offer a "transcribe during recording" option. Its default SHALL come from Settings and SHALL be on when WhisperKit is available, and the user MUST be able to override it for a single recording in the start dialog and on the recording screen while recording. The choice MUST be stored on the recording.

#### Scenario: Default from Settings

- **WHEN** the Settings default is on and the user opens the start dialog
- **THEN** the option is pre-checked for this recording

#### Scenario: Override for one recording

- **WHEN** the user unchecks the option in the start dialog
- **THEN** this recording is only transcribed after it stops
- **AND** the Settings default is unchanged

### Requirement: Only the low-resource engine runs during recording

Transcription during recording SHALL run only with the WhisperKit engine. When WhisperKit or its model is unavailable, the option MUST be shown as unavailable with the reason, and the recording is transcribed after stop as usual. The CPU fallback engine MUST NOT run during a recording.

#### Scenario: WhisperKit unavailable

- **WHEN** the WhisperKit model is not installed
- **THEN** the option is disabled in the start dialog and on the recording screen with the reason
- **AND** transcription starts after stop

### Requirement: Final windows are committed while recording

With the option on, the system SHALL finalize windows of about 3 minutes (the window-length setting) during the recording as soon as both tracks have audio on disk past the window's cut point plus a safety margin of at least 2 seconds, using the same windowing, two-track commit, and `final_until_s` boundary as the after-stop pass.

#### Scenario: Windows finalize during a call

- **WHEN** a recording with the option on has been running for 10 minutes
- **THEN** final segments exist for roughly the first 6–9 minutes for both tracks

#### Scenario: Catch up when turned on mid-recording

- **WHEN** the user turns the option on 20 minutes into a recording
- **THEN** the system starts finalizing from the beginning and catches up while recording continues

#### Scenario: Turned off mid-recording

- **WHEN** the user turns the option off during a recording
- **THEN** no new window starts; the window in progress may finish; the rest is transcribed after stop

### Requirement: Live transcription pauses in Low Power Mode

Transcription during recording SHALL keep running on battery but SHALL pause while Low Power Mode is on, and resume (catching up) when Low Power Mode ends; anything left is done after stop.

#### Scenario: Low Power Mode during a call

- **WHEN** Low Power Mode turns on 20 minutes into a recording with the option on
- **THEN** no new window starts while it stays on
- **AND** the recording screen shows that live transcription is paused for Low Power Mode

### Requirement: Recording is never harmed by transcription

Transcription during recording SHALL NOT block, delay, or drop captured audio. If the engine falls behind, it MUST keep working through the backlog (and finish it after stop); if it fails, recording MUST continue and the remaining windows MUST be transcribed after stop.

#### Scenario: Engine crash during a call

- **WHEN** the speech helper exits during a recording
- **THEN** the recording continues unaffected
- **AND** the untranscribed windows are processed after stop

### Requirement: Stop and trim cannot race live windows

Stopping a recording SHALL end transcription during recording before the stop completes: a window in flight is either committed before stop returns or discarded and redone after stop. No live window MUST commit after the stop has returned.

#### Scenario: Window in flight at stop

- **WHEN** the user stops while a live window is being transcribed
- **THEN** either it commits before stop returns or it is transcribed again after stop
- **AND** a following trim sees a consistent set of segments

### Requirement: Live work shares the engine with queued jobs

Transcription during recording SHALL run outside the job queue and share the speech helper with any running job through a single request lock, so speech work is never run in parallel.

#### Scenario: Earlier recording still processing

- **WHEN** a new recording with the option on starts while an earlier recording's job is still running
- **THEN** both progress, one request at a time
- **AND** the new recording's backlog is finished after it stops if needed

### Requirement: After stop only the remainder runs

When a recording with live-finalized windows stops, the job SHALL transcribe only the windows not yet final, then run diarization, summary, and compression as usual.

#### Scenario: Short tail after a long call

- **WHEN** a 60-minute recording stops with final windows up to 57:00
- **THEN** only 57:00–60:00 is transcribed before diarization starts

### Requirement: Trim keeps live results consistent

When the user trims a recording after stop, all its segments (final and draft) and its stored `final_until_s` SHALL be shifted to the trimmed timeline, and segments starting outside the kept range MUST be deleted, so the transcript matches the trimmed audio.

#### Scenario: Leading silence trimmed

- **WHEN** live final segments exist and the user trims the first 2:00
- **THEN** segments before 2:00 are deleted and all remaining segment times are reduced by 120 s
