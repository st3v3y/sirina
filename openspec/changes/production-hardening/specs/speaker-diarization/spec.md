## ADDED Requirements

### Requirement: Diarization runs in the packaged app

When enabled with a valid token, speaker diarization SHALL run in the packaged application, not only in a development checkout. The diarization runtime SHALL be bundled with the app, and model weights SHALL be downloaded once and cached under the app data directory.

#### Scenario: Diarization works in the packaged app

- **WHEN** diarization is enabled with a valid token in the packaged app and a recording is processed
- **THEN** speakers are separated and labelled using the bundled runtime

#### Scenario: Weights cached on first use

- **WHEN** diarization runs for the first time
- **THEN** the model weights are downloaded once and reused from the app data directory on later runs

#### Scenario: Disabled by default

- **WHEN** the app is freshly installed
- **THEN** diarization remains disabled until the user explicitly enables it
