## ADDED Requirements

### Requirement: Speech models are downloaded on demand, never bundled

The app bundle SHALL NOT contain speech model weights. Models SHALL be downloaded into the app's data directory when first needed or when the user installs them, and reused afterwards.

#### Scenario: First use downloads the model

- **WHEN** the selected final model is not installed and a recording needs transcription
- **THEN** the model is downloaded once into the data directory and then used
- **AND** progress shows that the model is downloading

### Requirement: Users can list, install, and delete models

The Settings page SHALL list the known speech models (final engine models, the CPU fallback model, and the caption/draft language asset) with name, engine, approximate size, install status, and whether it is in use. Users MUST be able to install a model and delete an installed model. Deleting the model in use MUST be refused while a job or transcription during recording is running and MUST otherwise warn that the next transcription will download it again or fall back.

#### Scenario: See installed models with size

- **WHEN** the user opens the model manager
- **THEN** each model shows its install status and size on disk

#### Scenario: Delete an unused model

- **WHEN** the user deletes an installed model that is not in use
- **THEN** its files are removed and the freed size is reflected in the list

#### Scenario: Delete refused while busy

- **WHEN** the user tries to delete the in-use model while a transcription job runs
- **THEN** the deletion is refused with an explanation

### Requirement: Download failures are recoverable

A failed or interrupted model download SHALL leave no partial model marked as installed, SHALL show an error with a retry action, and the job SHALL fall back to an installed engine when one exists.

#### Scenario: Offline first run

- **WHEN** the WhisperKit model cannot be downloaded because the Mac is offline
- **THEN** the model shows as not installed with a retry action
- **AND** transcription uses the faster-whisper fallback if its model is installed, otherwise the job fails with a clear message
