## MODIFIED Requirements

### Requirement: High-quality offline transcription settings

Transcription SHALL use offline-quality settings rather than the realtime path: a configurable model (defaulting to a quality-oriented model), voice-activity filtering, and word-level timestamps. Beam search SHALL be used where the active engine supports it. The final pass MAY process a recording in time windows (see "Final transcript is produced window by window"), but each window MUST be cut at a silence so no word is split across windows. Language SHALL be detected once per recording (on the first window that contains speech) and reused for the remaining windows, unless a language is configured. Vocabulary hints (`WHISPER_INITIAL_PROMPT`) MUST still be applied where the active engine supports them. These guarantees are engine-independent.

#### Scenario: Windowed transcription with quality settings

- **WHEN** a recording is transcribed
- **THEN** each window is transcribed with the offline-quality settings of the active engine
- **AND** word-level timestamps are produced for every track
- **AND** no window boundary falls inside detected speech

#### Scenario: Language detected once

- **WHEN** no transcription language is configured
- **THEN** the language detected on the first window with speech is used for all later windows of that recording

#### Scenario: Forced language honored

- **WHEN** a transcription language is configured
- **THEN** detection is skipped and the configured language is used

### Requirement: Transcription engine is selected by hardware and availability

The system SHALL select a final transcription engine at startup behind a single interface: when configured for automatic selection, it MUST use the native WhisperKit engine on Apple Silicon when the bundled speech helper is present and its configured model is installed, and otherwise use the CPU faster-whisper engine. The MLX engine MUST NOT be chosen by automatic selection. Selection MUST be overridable by configuration, and the chosen engine MUST be fixed for the lifetime of the process (until an explicit engine reload).

#### Scenario: WhisperKit is used when available

- **WHEN** the app runs on Apple Silicon, the speech helper is bundled, the WhisperKit model is installed, and automatic selection is in effect
- **THEN** transcription uses the WhisperKit engine

#### Scenario: Fallback when WhisperKit is unavailable

- **WHEN** the app does not run on Apple Silicon, or the speech helper is missing, or it fails to start, or its model is not installed
- **THEN** transcription uses the faster-whisper engine
- **AND** the reason for the fallback is recorded so Settings can show it

#### Scenario: Configuration overrides selection

- **WHEN** a specific engine is configured
- **THEN** that engine is used regardless of hardware detection, falling back to faster-whisper only if the configured engine cannot start

#### Scenario: Engines satisfy the same interface

- **WHEN** any engine transcribes a window of a track
- **THEN** it returns transcript lines with word timestamps and a detected/configured language in the same shape
- **AND** downstream diarization and summary stages are unaffected by which engine ran

### Requirement: Chunked transcription for non-streaming engines

Every engine SHALL be driven window by window by the job, and progress SHALL be reported after each window so that it reflects work actually completed. Segment and word timestamps MUST be offset to absolute recording time. The window length MUST be configurable.

#### Scenario: Windows produce a measured fraction

- **WHEN** any engine transcribes a recording
- **THEN** progress advances as each window completes, reflecting completed audio over total audio

#### Scenario: Timestamps are absolute

- **WHEN** a window starting at offset T is transcribed
- **THEN** its segment/word times are shifted by T so the combined transcript is correctly ordered

#### Scenario: Window length is configurable

- **WHEN** the window length setting is changed
- **THEN** later jobs cut windows of approximately that length (adjusted to the nearest common silence)

### Requirement: Transcript is persisted before the summary

The job SHALL persist final transcript segments window by window as each window completes (with the baseline speaker split), before diarization refinement and before summary generation. The summary SHALL be generated as the final step from the final (not draft) transcript, and the recording becomes `ready` only after the summary attempt.

#### Scenario: Segments exist before summarizing

- **WHEN** the final pass of a recording completes
- **THEN** its final transcript segments are stored before the summary is generated

#### Scenario: Final segments are stored per window

- **WHEN** a window of the final pass completes
- **THEN** that window's final segments for all tracks are stored before the next window starts

#### Scenario: Ready still means transcript plus summary

- **WHEN** a recording becomes `ready` after a completed final pass
- **THEN** both its final transcript and its auto-summary (when the transcript is non-empty) are present
- **AND** no draft segments remain for that recording

#### Scenario: Ready after a stopped pass keeps drafts marked

- **WHEN** the user stops processing before the final pass completes
- **THEN** the recording becomes `ready` with its finalized windows final and the rest still marked draft
- **AND** no summary is generated from draft segments

## ADDED Requirements

### Requirement: Final segments keep word timings for speaker splitting

Final segments SHALL store their word timings, and the diarization stage SHALL rebuild each track's lines (with words) from the stored final segments, so speaker splitting and echo suppression work no matter in which process or session the windows were finalized.

#### Scenario: Diarization after a restart

- **WHEN** the backend restarts after some windows were finalized and the job later reaches diarization
- **THEN** speakers are split at word level using the stored word timings of all final windows

### Requirement: Jobs resume from the last final window

The last committed window end SHALL be stored on the recording. A job for a recording that already has final windows (after a restart, or from transcription during recording) MUST continue after that point instead of starting over. Reprocessing a recording MUST clear its segments, speakers, and stored boundary first and rebuild from the start.

#### Scenario: Restart mid-job

- **WHEN** the backend restarts after windows up to 24:00 were committed
- **THEN** the re-enqueued job transcribes from 24:00 onward

#### Scenario: Reprocess rebuilds

- **WHEN** the user reprocesses a `ready` recording
- **THEN** all its segments and speakers are cleared and transcription starts at 0:00

### Requirement: CPU engine uses performance cores by default

When no thread count is configured, the faster-whisper engine SHALL use one thread per performance core on hardware that reports performance cores (Apple Silicon), and all cores otherwise. A configured thread count MUST override this.

#### Scenario: Apple Silicon default

- **WHEN** the CPU engine loads on a Mac with 6 performance and 2 efficiency cores and no thread count is configured
- **THEN** it uses 6 threads

#### Scenario: Configured thread count wins

- **WHEN** a thread count is configured
- **THEN** the CPU engine uses exactly that count

### Requirement: Idle sleep is prevented until processing finishes

The system SHALL prevent idle system sleep from the start of a recording until its post-recording processing reaches a terminal state (`ready` or `failed`) or is stopped by the user. The guard MUST be released when no recording is active and no processing job is running. Lid-close sleep is not covered.

#### Scenario: Guard spans recording and processing

- **WHEN** a recording stops and its processing job starts
- **THEN** idle sleep stays prevented until that job ends

#### Scenario: Guard released when idle

- **WHEN** the last processing job ends and no recording is active
- **THEN** the idle-sleep guard is released
