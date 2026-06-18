# local-only-runtime Specification

## Purpose
TBD - created by archiving change strip-discord. Update Purpose after archive.
## Requirements
### Requirement: Single local process with no Discord dependency

The application SHALL run as a single local backend process that has no dependency on Discord libraries, tokens, or gateway connections. The process MUST start successfully without any Discord configuration present.

#### Scenario: Backend starts with no Discord configuration

- **WHEN** the backend is started and no `DISCORD_TOKEN` or `DISCORD_GUILD_ID` is set
- **THEN** the process starts successfully and serves the API
- **AND** no attempt is made to connect to the Discord gateway

#### Scenario: Discord packages are absent

- **WHEN** the project's dependencies are installed
- **THEN** no Discord library (`discord.py`, `py-cord`, `discord-ext-voice-recv`) is present in the environment

### Requirement: Local audio is the only recording source

The start-recording flow SHALL accept only the local audio source. The API and UI MUST NOT expose a Discord source, voice-channel selection, or guild configuration.

#### Scenario: Start recording uses local audio only

- **WHEN** a client requests to start a recording
- **THEN** the request targets a local audio input device
- **AND** there is no parameter to select a Discord channel or guild

#### Scenario: Dashboard offers no Discord option

- **WHEN** the user opens the dashboard
- **THEN** no Discord/local source toggle or voice-channel-ID input is shown

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

### Requirement: Inference is local-first; cloud is opt-in

By default, all transcription and LLM inference SHALL run locally with no data leaving the device. Sending data to a third-party (cloud) service SHALL only occur when the user explicitly selects a cloud LLM provider, and that choice MUST be disclosed.

#### Scenario: Default keeps data on-device

- **WHEN** the app runs without the user selecting a cloud provider
- **THEN** no transcript or audio is sent to any external service

#### Scenario: Cloud is an explicit, disclosed choice

- **WHEN** the user selects a cloud LLM provider
- **THEN** transcripts are sent to that provider only for the AI features
- **AND** the choice was made explicitly and disclosed

