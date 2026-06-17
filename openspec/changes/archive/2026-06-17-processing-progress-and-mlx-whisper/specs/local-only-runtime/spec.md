## MODIFIED Requirements

### Requirement: Status reflects local capabilities only

The status endpoint SHALL report the health of local capabilities (transcription model loaded, LLM reachable) and the active transcription engine, and MUST NOT report Discord connection state.

#### Scenario: Status omits Discord fields

- **WHEN** a client requests application status
- **THEN** the response contains no `bot_connected` or `voice_channel` fields
- **AND** it reports whether the transcription model is loaded and the LLM is reachable

#### Scenario: Status reports the active transcription engine

- **WHEN** a client requests application status
- **THEN** the response indicates which transcription engine is active (e.g. MLX or faster-whisper)
