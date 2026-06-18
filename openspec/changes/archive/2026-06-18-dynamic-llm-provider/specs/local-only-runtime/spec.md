## ADDED Requirements

### Requirement: Inference is local-first; cloud is opt-in

By default, all transcription and LLM inference SHALL run locally with no data leaving the device. Sending data to a third-party (cloud) service SHALL only occur when the user explicitly selects a cloud LLM provider, and that choice MUST be disclosed.

#### Scenario: Default keeps data on-device

- **WHEN** the app runs without the user selecting a cloud provider
- **THEN** no transcript or audio is sent to any external service

#### Scenario: Cloud is an explicit, disclosed choice

- **WHEN** the user selects a cloud LLM provider
- **THEN** transcripts are sent to that provider only for the AI features
- **AND** the choice was made explicitly and disclosed

## MODIFIED Requirements

### Requirement: Status reflects local capabilities only

The status endpoint SHALL report the health of local capabilities (transcription model loaded, LLM reachable), the active transcription engine, and the active LLM provider/model, and MUST NOT report Discord connection state.

#### Scenario: Status omits Discord fields

- **WHEN** a client requests application status
- **THEN** the response contains no `bot_connected` or `voice_channel` fields
- **AND** it reports whether the transcription model is loaded and the LLM is reachable

#### Scenario: Status reports the active transcription engine

- **WHEN** a client requests application status
- **THEN** the response indicates which transcription engine is active (e.g. MLX or faster-whisper)

#### Scenario: Status reports the active LLM provider

- **WHEN** a client requests application status
- **THEN** the response indicates the active LLM provider and model
