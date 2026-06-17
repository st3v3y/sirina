# transcription-job Specification

## Purpose
TBD - created by archiving change offline-transcription. Update Purpose after archive.
## Requirements
### Requirement: Transcription runs after a recording stops

When a recording is stopped (status `processing`), the system SHALL transcribe its audio in the background and, on success, persist the transcript and set the recording status to `ready`.

#### Scenario: Stopped recording becomes ready with a transcript

- **WHEN** a recording is stopped and its audio contains speech
- **THEN** the system transcribes the audio and stores `Segment` rows with start time, end time, and text
- **AND** the recording status becomes `ready`

#### Scenario: Transcription failure is recorded

- **WHEN** transcription of a recording raises an error
- **THEN** the recording status becomes `failed`
- **AND** an error message is stored on the recording

### Requirement: One job at a time, restart-safe

Transcription jobs SHALL run one at a time through a queue. On startup, any recording left in `processing` (e.g. due to a crash or restart) MUST be re-enqueued.

#### Scenario: Jobs do not run concurrently

- **WHEN** two recordings are stopped in quick succession
- **THEN** their transcription jobs run sequentially, not simultaneously

#### Scenario: Pending recordings resume after restart

- **WHEN** the backend starts and a recording is in `processing` with no transcript
- **THEN** that recording is re-enqueued for transcription

### Requirement: High-quality offline transcription settings

Transcription SHALL use offline-quality settings rather than the realtime path: a configurable model (defaulting to a quality-oriented model), beam search, voice-activity filtering, and word-level timestamps when needed for speaker alignment. Language SHALL be detected once over the whole file unless a language is configured. Vocabulary hints (`WHISPER_INITIAL_PROMPT`) MUST still be applied where the active engine supports them. These guarantees are engine-independent.

#### Scenario: Whole-file transcription with quality settings

- **WHEN** a recording is transcribed
- **THEN** the whole audio file is processed at once (not in short realtime chunks)
- **AND** word-level timestamps are produced when the track will be diarized, for speaker alignment

#### Scenario: Forced language honored

- **WHEN** a transcription language is configured
- **THEN** detection is skipped and the configured language is used

### Requirement: Detected language is stored

The detected (or configured) language of a recording SHALL be stored on the recording.

#### Scenario: Language persisted on completion

- **WHEN** a recording finishes transcription
- **THEN** its language code is stored on the recording

### Requirement: Transcription engine is selected by hardware and availability

The system SHALL select a transcription engine at startup behind a single interface: when configured for automatic selection, it MUST use an Apple-GPU (MLX) engine on Apple Silicon when that engine is available, and otherwise use the CPU faster-whisper engine. Selection MUST be overridable by configuration, and the chosen engine MUST be fixed for the lifetime of the process.

#### Scenario: Apple GPU is used when available

- **WHEN** the app runs on Apple Silicon and the MLX engine is importable and automatic selection is in effect
- **THEN** transcription uses the MLX engine

#### Scenario: Fallback when MLX is unavailable

- **WHEN** the app does not run on Apple Silicon or the MLX engine is unavailable
- **THEN** transcription uses the faster-whisper engine

#### Scenario: Configuration overrides selection

- **WHEN** a specific engine is configured
- **THEN** that engine is used regardless of hardware detection

#### Scenario: Both engines satisfy the same interface

- **WHEN** either engine transcribes a file
- **THEN** it returns transcript lines and a detected/configured language in the same shape
- **AND** downstream diarization and summary stages are unaffected by which engine ran

### Requirement: Chunked transcription for non-streaming engines

For an engine that does not stream per-segment progress, transcription SHALL process the audio in fixed-size windows and report progress after each window, so that progress reflects work actually completed. Segment and word timestamps MUST be offset to absolute recording time. Chunking MUST be configurable and may be disabled.

#### Scenario: Windows produce a measured fraction

- **WHEN** a non-streaming engine transcribes a recording with chunking enabled
- **THEN** progress advances as each window completes, reflecting completed audio over total audio

#### Scenario: Timestamps are absolute

- **WHEN** a window starting at offset T is transcribed
- **THEN** its segment/word times are shifted by T so the combined transcript is correctly ordered

#### Scenario: Chunking can be disabled

- **WHEN** chunking is disabled by configuration
- **THEN** the engine transcribes in a single pass (progress falls back to the prior behavior)

### Requirement: Silent tracks are skipped

A track whose audio is effectively silent (peak amplitude below a configurable threshold) SHALL NOT be transcribed, and SHALL NOT produce a speaker. This prevents engines without voice-activity filtering (e.g. MLX) from hallucinating text on silence — such as an empty system/loopback capture when nothing is playing.

#### Scenario: Silent system track produces no speaker

- **WHEN** a two-track recording's system track is silent (e.g. nothing played through the loopback)
- **THEN** the system track is not transcribed
- **AND** no "Others" speaker or segments are created from it
- **AND** the microphone track is transcribed normally

#### Scenario: Non-silent tracks are unaffected

- **WHEN** a track contains audio above the silence threshold
- **THEN** it is transcribed as usual

### Requirement: Transcript is persisted before the summary

The job SHALL persist transcript segments as soon as transcription completes (with the baseline speaker split), before diarization refinement and before summary generation. The summary SHALL be generated as the final step, and the recording becomes `ready` only after the summary attempt.

#### Scenario: Segments exist before summarizing

- **WHEN** transcription of a recording completes
- **THEN** its transcript segments are stored before the summary is generated

#### Scenario: Ready still means transcript plus summary

- **WHEN** a recording becomes `ready`
- **THEN** both its transcript and its auto-summary (when the transcript is non-empty) are present

