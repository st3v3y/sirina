## ADDED Requirements

### Requirement: The model in use follows the active engine's configuration

The model manager SHALL mark as "in use" exactly the models the active engine loads:
- the configured faster-whisper model (e.g. `medium`) when faster-whisper is active or is the fallback
- the Parakeet model when Parakeet is active
- the WhisperKit model when WhisperKit is active

A model in use MUST NOT be listed as "no longer used", and the rule that deletion is refused while busy MUST apply to it.

#### Scenario: Configured faster-whisper model is in use

- **WHEN** faster-whisper is active with the model setting `medium`
- **THEN** the `medium` model is listed as in use, not under "No longer used"
- **AND** deleting it while a job runs is refused

#### Scenario: Parakeet in use

- **WHEN** Parakeet is the active engine
- **THEN** its model is marked in use and the WhisperKit and faster-whisper models are not
