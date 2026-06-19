## ADDED Requirements

### Requirement: The UI recovers from render errors

A render error in any screen SHALL be caught by an error boundary and shown as a recoverable message (with a reload), rather than leaving a blank screen.

#### Scenario: A screen throws during render

- **WHEN** a screen throws an error while rendering
- **THEN** an error boundary shows a recoverable message with a way to reload
- **AND** the app does not show a blank/white screen

### Requirement: Startup and readiness failures are actionable

When the backend is unreachable, or first-run transcription-model setup fails (e.g. offline), the startup/readiness experience SHALL show a clear, actionable message with a retry, rather than waiting indefinitely.

#### Scenario: Backend unreachable beyond a threshold

- **WHEN** the backend stays unreachable past a reasonable threshold
- **THEN** the startup view explains the problem and offers a retry

#### Scenario: Transcription model fails to load

- **WHEN** the first-run transcription model fails to download or load (e.g. offline)
- **THEN** the app surfaces that transcription is unavailable, with the reason and a retry
- **AND** it does not present a perpetual "loading" state with silently failing transcription

### Requirement: Branded startup screen

The startup/loading screen SHALL present the app's branding (logo and name) in the active theme and indicate the current startup phase, rather than an unbranded spinner. It SHALL host the startup phase and the failure/retry states in the same view.

#### Scenario: Startup screen is branded and themed

- **WHEN** the app is starting and the backend is not yet ready
- **THEN** the startup screen shows the Sirina logo and wordmark in the active theme
- **AND** it indicates the current phase (e.g. starting, downloading the transcription model)
