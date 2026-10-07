## ADDED Requirements

### Requirement: Per-recording processing options in the start dialog

The start dialog SHALL show two per-recording options, pre-set from the Settings defaults: "Live captions" and "Transcribe during recording". An option that is unavailable on this Mac MUST be shown disabled with the reason. The chosen values MUST apply to this recording only.

#### Scenario: Options pre-set from Settings

- **WHEN** the user opens the start dialog
- **THEN** both options reflect the Settings defaults

#### Scenario: One-off change

- **WHEN** the user turns "Transcribe during recording" off in the dialog and starts
- **THEN** this recording runs without it and the next dialog again shows the Settings default
