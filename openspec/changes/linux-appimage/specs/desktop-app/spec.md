## MODIFIED Requirements

### Requirement: Single launchable macOS app

The product SHALL be distributable as a single desktop application for each supported platform:
- **macOS**: an `.app`
- **Windows**: an NSIS installer
- **Linux**: an AppImage and a `.deb`

When launched, the application starts the local backend and serves the UI without the user running any terminal commands. Packaging SHALL leave the frozen backend's files unchanged on every platform.

#### Scenario: Launch starts everything

- **WHEN** the user opens the packaged app on macOS, Windows or Linux
- **THEN** the backend starts automatically (as a bundled sidecar)
- **AND** the UI is shown, talking to the local backend

#### Scenario: Quit stops the backend

- **WHEN** the user quits the app
- **THEN** the bundled backend process is stopped

#### Scenario: Platform helpers are located per platform

- **WHEN** the packaged app starts on any platform
- **THEN** the backend receives the paths of the native helpers bundled for that platform
- **AND** helpers that do not exist on that platform are passed as absent, not as broken paths

#### Scenario: The AppImage starts its bundled backend

- **WHEN** the user runs the Linux AppImage
- **THEN** the shell starts the backend from inside the AppImage
- **AND** the backend's files are identical to the PyInstaller build's output

### Requirement: Unsigned distribution that can be opened

The app SHALL be distributable without paid code-signing certificates, with documented steps for opening it on each platform:
- **macOS**: past Gatekeeper.
- **Windows**: past the SmartScreen "unrecognized app" prompt.
- **Linux**: run as an AppImage (made executable) or installed from the `.deb`.

#### Scenario: Opening an unsigned build

- **WHEN** the user opens an unsigned build for the first time
- **THEN** documented steps allow it to run: right-click → Open or clearing quarantine on macOS, "More info → Run anyway" on Windows, `chmod +x` for the AppImage (or `sudo apt install ./Sirina_*.deb`) on Linux
