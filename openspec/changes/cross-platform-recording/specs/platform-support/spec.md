## ADDED Requirements

### Requirement: Supported platforms

The app SHALL support macOS on Apple Silicon, Windows 10/11 on x64, and Linux on x64. Linux support means glibc-based distributions with WebKitGTK 4.1, and PulseAudio or PipeWire with pipewire-pulse. On every supported platform, the app MUST record the microphone and the system audio as separate tracks, mix them for playback, and transcribe and summarize the recording.

#### Scenario: Recording a call on Windows

- **WHEN** a Windows user starts a recording with microphone and native system audio
- **THEN** `mic.wav` and `system.wav` are written as separate tracks and `mixed.wav` is produced on stop
- **AND** the recording is transcribed and summarized after stop

#### Scenario: Recording a call on Linux

- **WHEN** a Linux user starts a recording with microphone and native system audio
- **THEN** both tracks are recorded and mixed exactly as on the other platforms

### Requirement: Unavailable features are reported with a reason

Capability endpoints SHALL report, for each platform-dependent feature, whether it is available, and when it isn't, a short user-facing reason. Platform-dependent features include:
- native system audio
- live captions
- transcription during recording
- speaker splitting
- each transcription engine

The UI MUST show that reason next to the disabled option instead of macOS-specific wording. The UI MUST NOT refer to "this Mac" or "macOS" on other platforms.

#### Scenario: Feature missing on this platform

- **WHEN** a feature is not available on the current platform (e.g. SpeakerKit speaker splitting on Windows)
- **THEN** the capabilities report it as unavailable with a reason naming the platform limitation
- **AND** the UI disables the option and shows that reason

#### Scenario: Platform-neutral copy

- **WHEN** the app runs on Windows or Linux
- **THEN** no settings, model or recording text refers to "this Mac" or to macOS-managed assets

#### Scenario: Native start rejected with the platform's reason

- **WHEN** a recording requests native system audio and the probe reports it unavailable
- **THEN** the start is rejected with that platform's reason (e.g. "no PulseAudio/PipeWire server" on Linux), not macOS permission instructions

#### Scenario: Model manager hides models this platform can't run

- **WHEN** the model manager is opened on Windows or Linux
- **THEN** WhisperKit, SpeakerKit and the Apple speech asset are not listed

### Requirement: Idle sleep is prevented on every platform

The recording and processing sleep prevention SHALL work on every supported platform:
- **macOS**: an IOKit power assertion.
- **Windows**: `SetThreadExecutionState` with system- and display-required flags, held by a dedicated thread.
- **Linux**: a logind idle/sleep inhibitor.

Where the mechanism is unavailable (e.g. a Linux system without logind), the blocker MUST degrade to a logged no-op and MUST NOT fail the recording.

#### Scenario: Windows stays awake while recording

- **WHEN** a recording is active on Windows and the user is idle
- **THEN** the system does not enter idle sleep until the recording stops and processing finishes

#### Scenario: Linux without logind

- **WHEN** the Linux system has no logind (no `systemd-inhibit`)
- **THEN** recording proceeds and a warning is logged that sleep cannot be prevented

### Requirement: Power state is read on every platform

The power state used for warnings and live-work pausing SHALL report whether the machine runs on battery on every platform. Low Power Mode detection MAY remain macOS-only and MUST report "off" elsewhere.

#### Scenario: Laptop on battery under Windows

- **WHEN** a Windows laptop runs on battery
- **THEN** the power state reports battery and the existing battery warning appears

### Requirement: Recorded audio is compressed on every platform

When audio compression is enabled, finished recordings SHALL be compressed to AAC (`.m4a`) on every platform. Compressed recordings MUST decode back to WAV for re-processing on any platform, independent of OS tools. Compressed recordings made by earlier macOS builds MUST remain readable.

#### Scenario: Compression on Linux

- **WHEN** a recording finishes on Linux with compression enabled
- **THEN** its tracks are stored as `.m4a` and the WAVs are removed only after the conversion is committed

#### Scenario: Re-processing an old macOS recording

- **WHEN** a recording compressed by an earlier `afconvert`-based build is re-processed
- **THEN** it decodes to WAV and processes normally

### Requirement: Helper processes are cleaned up on every platform

On startup the backend SHALL terminate orphaned capture helpers left by a previous crashed run, on every platform, without relying on platform-specific command-line tools. It MUST only terminate processes whose executable is Sirina's own bundled helper.

#### Scenario: Orphan after a crash on Windows

- **WHEN** the backend starts and an orphaned `system-audio-capture.exe` from the bundled path is running
- **THEN** that process is terminated before any new recording starts
- **AND** unrelated processes with a similar name are left alone

### Requirement: Every platform is built in CI

A CI workflow SHALL build the frontend, the backend, the native helpers and the desktop bundle for macOS arm64, Windows x64 and Linux x64, and SHALL run the backend test suite on each. Bundles MUST be uploaded as build artifacts. CI MUST NOT publish releases or require signing secrets.

#### Scenario: Pull request builds all platforms

- **WHEN** a pull request is opened or updated
- **THEN** CI builds bundles for all three platforms and reports failures per platform
- **AND** the bundles are downloadable from the run
