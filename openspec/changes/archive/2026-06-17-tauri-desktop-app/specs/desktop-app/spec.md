## ADDED Requirements

### Requirement: Single launchable macOS app

The product SHALL be distributable as a single macOS application that, when launched, starts the local backend and serves the UI without the user running any terminal commands.

#### Scenario: Launch starts everything

- **WHEN** the user opens the packaged app
- **THEN** the backend starts automatically (as a bundled sidecar)
- **AND** the UI is shown, talking to the local backend

#### Scenario: Quit stops the backend

- **WHEN** the user quits the app
- **THEN** the bundled backend process is stopped

### Requirement: Permissions requested on first run

The app SHALL declare and request the macOS permissions it needs (Microphone, and Screen Recording for system audio), prompting the user on first use.

#### Scenario: First-run permission prompts

- **WHEN** the app needs microphone or system-audio access for the first time
- **THEN** the user is prompted to grant the corresponding macOS permission

### Requirement: Unsigned distribution that can be opened

The app SHALL be distributable without an Apple Developer subscription (unsigned / ad-hoc signed), with a documented way for the user to open it past Gatekeeper.

#### Scenario: Opening an unsigned build

- **WHEN** the user opens an unsigned build for the first time
- **THEN** documented steps (e.g. right-click → Open, or clearing the quarantine attribute) allow it to run

### Requirement: Development flow preserved

The existing two-server development flow SHALL continue to work; the packaged app is the distribution wrapper, not a replacement for local development.

#### Scenario: Dev servers still run

- **WHEN** a developer runs the existing dev workflow
- **THEN** the backend and frontend dev servers run as before, independent of the packaged app
