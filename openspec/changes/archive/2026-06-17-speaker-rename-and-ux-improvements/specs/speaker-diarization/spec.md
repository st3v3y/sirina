## ADDED Requirements

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
