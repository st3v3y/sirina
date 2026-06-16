## MODIFIED Requirements

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
