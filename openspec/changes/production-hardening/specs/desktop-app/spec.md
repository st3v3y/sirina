## ADDED Requirements

### Requirement: OS permission grants persist across launches

The packaged application SHALL be signed with a stable identity so that operating-system permission grants (e.g. macOS Screen Recording / TCC) persist across launches and rebuilds and are not requested again every time. The build MUST NOT silently fall back to ad-hoc signing without surfacing that permissions will not persist.

#### Scenario: A granted permission is remembered

- **WHEN** the user grants Screen Recording permission and relaunches the app
- **THEN** the app retains the grant and does not prompt again

#### Scenario: Ad-hoc fallback is surfaced

- **WHEN** the app is built without a stable signing identity
- **THEN** the build reports that it is ad-hoc signed and that OS permissions will re-prompt

### Requirement: Backend failures are surfaced, not hung

The app SHALL detect when the bundled backend fails to start or exits unexpectedly and surface an actionable error with a retry, rather than showing the startup state indefinitely.

#### Scenario: Backend never becomes ready

- **WHEN** the backend does not become reachable within a reasonable timeout
- **THEN** the app shows an actionable error with a retry option instead of an endless startup splash

#### Scenario: Backend exits after startup

- **WHEN** the backend process exits unexpectedly after the app has started
- **THEN** the app surfaces that the backend stopped and offers to restart/retry

### Requirement: A single instance runs at a time

Launching the app while it is already running SHALL focus the existing window rather than starting a second backend.

#### Scenario: Second launch focuses the existing window

- **WHEN** the user launches the app while an instance is already running
- **THEN** the existing window is focused and no second backend is spawned

### Requirement: Backend logs are persisted for diagnostics

The app SHALL write backend logs to a rotating file under the app data directory, and MUST NOT write secret values to the log.

#### Scenario: A log file is available after a run

- **WHEN** the app has run
- **THEN** a rotating log file exists under the app data directory
- **AND** it contains no secret values (tokens / API keys)

### Requirement: The app starts promptly

The packaged backend SHALL NOT re-extract its entire bundle on every launch, and the app SHALL reach a usable state without blocking on optional or background model loading.

#### Scenario: Repeat launches don't re-extract

- **WHEN** the app is launched after the first run
- **THEN** it does not re-extract the full backend bundle on each launch

#### Scenario: Usable before models finish loading

- **WHEN** the backend has started but the transcription model is still loading
- **THEN** the app is usable and shows the model as still loading, rather than blocking startup
