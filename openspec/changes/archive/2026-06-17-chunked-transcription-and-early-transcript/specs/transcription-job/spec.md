## ADDED Requirements

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
