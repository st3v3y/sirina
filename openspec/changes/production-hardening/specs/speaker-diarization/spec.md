## ADDED Requirements

### Requirement: Diarization runs in the packaged app via an on-demand model

Speaker diarization SHALL run in the packaged application using a bundled ONNX runtime and a diarization model that is **downloaded on demand** (not bundled). The model SHALL be downloaded only when the user explicitly enables/installs diarization, cached under the app data directory, and reused thereafter. Diarization SHALL be disabled by default, and enabling it SHALL require the model to be present.

#### Scenario: Model downloaded on explicit enable

- **WHEN** the user installs/enables diarization
- **THEN** the diarization model is downloaded once and cached under the app data directory

#### Scenario: Diarization works in the packaged app

- **WHEN** diarization is enabled with the model present and a recording is processed
- **THEN** speakers are separated and labelled using the bundled ONNX runtime

#### Scenario: Disabled by default; no heavy framework bundled

- **WHEN** the app is freshly installed
- **THEN** diarization is disabled and its model is not present until the user installs it
- **AND** the application bundle does not include a multi-hundred-MB ML framework solely for diarization
