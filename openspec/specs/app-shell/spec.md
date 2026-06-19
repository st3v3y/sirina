# app-shell Specification

## Purpose
TBD - created by archiving change ui-redesign. Update Purpose after archive.
## Requirements
### Requirement: Persistent navigation sidebar

The application SHALL present a persistent left sidebar on every primary screen that provides navigation to Recordings, Ask, People, Templates, and Settings, and SHALL indicate which destination is currently active. Navigating between destinations MUST keep the sidebar in place.

#### Scenario: Sidebar is present on every screen

- **WHEN** the user is on any primary screen (Recordings, a recording's detail, Ask, People, Templates, or Settings)
- **THEN** the left sidebar with the navigation items is shown
- **AND** the item for the current screen is marked active

#### Scenario: Navigating keeps the shell

- **WHEN** the user selects a different navigation item
- **THEN** the destination renders in the main area while the sidebar remains in place

### Requirement: Record control is available globally

The sidebar SHALL provide the Record control and an entry point for selecting capture devices from every screen — not only from the recordings list — and SHALL reflect live recording state while a recording is in progress.

#### Scenario: Start a recording from anywhere

- **WHEN** the user activates the sidebar Record control from any screen
- **THEN** a recording starts using the selected capture devices

#### Scenario: Sidebar reflects live recording

- **WHEN** a recording is in progress
- **THEN** the sidebar Record control shows the live recording state (e.g. an active indicator and elapsed time)

#### Scenario: Device selection entry point is preserved

- **WHEN** the user opens device selection from the sidebar
- **THEN** the existing device-selection flow is shown and the last-used devices are still remembered

### Requirement: Tags are surfaced in the sidebar

The sidebar SHALL list the user's tags and provide entry points to create a tag and to filter recordings by tag, without changing tag management behavior.

#### Scenario: Filter by a sidebar tag

- **WHEN** the user selects a tag in the sidebar
- **THEN** the recordings list is filtered to that tag

#### Scenario: Create a tag from the sidebar

- **WHEN** the user uses the sidebar's new-tag entry point
- **THEN** a tag can be created as before

### Requirement: Persistent runtime status

The sidebar SHALL show a persistent indicator of local runtime readiness (at minimum whether transcription is ready and whether the LLM provider is reachable).

#### Scenario: Status reflects readiness

- **WHEN** the transcription model is loaded and the LLM provider is reachable
- **THEN** the sidebar status shows a ready/local state
- **AND** when a dependency is not ready, the status reflects that instead

### Requirement: Light and dark themes

The application SHALL provide both a light and a dark "paper & ink" theme. It SHALL default to the operating system's color-scheme preference, SHALL let the user override the theme, and SHALL persist that choice across launches. The active theme MUST apply before the first paint (no flash of the wrong theme).

#### Scenario: Default follows the OS

- **WHEN** the app loads for the first time with no saved preference
- **THEN** the theme matches the OS color-scheme preference

#### Scenario: Manual override persists

- **WHEN** the user selects a theme (light or dark)
- **THEN** that theme is applied immediately and used again on the next launch

#### Scenario: No flash of the wrong theme

- **WHEN** the app starts
- **THEN** the resolved theme is applied before the first paint

### Requirement: UI assets are bundled and load offline

All UI assets required for the theme — including fonts and icons — SHALL be bundled with the application. The app MUST NOT fetch fonts, icons, or other UI assets from an external network service (including an icon API) at runtime.

#### Scenario: Fonts and icons load without network access

- **WHEN** the app runs with no internet connection
- **THEN** the editorial fonts and icons render correctly from bundled assets
- **AND** no request is made to an external font, icon, or asset host (e.g. the Iconify API)

### Requirement: Existing controls are preserved across the restyle

Restyling a screen SHALL preserve every functional control, action, and route that exists before the redesign. A control absent from the new design comps MUST be kept (restyled), not removed.

#### Scenario: A control not shown in the comps still works

- **WHEN** a screen is restyled to the new design
- **THEN** controls and actions that existed before the redesign remain present and functional
- **AND** no route or handler is removed as part of the restyle

### Requirement: Accessible interaction in the light theme

Interactive elements SHALL have a visible focus indicator and remain operable by keyboard, and content text SHALL meet WCAG AA contrast against its background.

#### Scenario: Keyboard focus is visible

- **WHEN** the user moves focus to an interactive element with the keyboard
- **THEN** a visible focus indicator is shown
- **AND** the element can be activated without a pointer

#### Scenario: Content text is legible

- **WHEN** content text is rendered on the light theme
- **THEN** its contrast against the background meets WCAG AA

